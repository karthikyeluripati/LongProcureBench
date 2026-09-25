"""Standard benchmark runner for LongProcureBench policies."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from jsonschema import Draft202012Validator, ValidationError

from .evaluator import LongProcureBenchEvaluator
from .runtime import EnvironmentError, LongProcureBenchEnv


class RunnerError(ValueError):
    """Raised for invalid runner configuration or policy output."""


@runtime_checkable
class AgentPolicy(Protocol):
    """Minimal policy interface consumed by BenchmarkRunner."""

    policy_id: str
    policy_kind: str

    def reset(self, state: dict[str, Any]) -> None:
        """Prepare for a new episode using agent-visible reset state."""

    def act(self, state: dict[str, Any]) -> dict[str, Any]:
        """Return one semantic action decision from agent-visible state."""


class BenchmarkRunner:
    """Execute one policy against one episode and produce a standard result."""

    RESULT_SCHEMA_VERSION = "0.1.0"
    RUNNER_VERSION = "0.1.0"
    DECISION_KEYS = {"type", "supplier_id", "arguments"}

    def __init__(self, repo_root: str | Path | None = None):
        self.repo_root = (
            Path(repo_root).resolve()
            if repo_root is not None
            else Path(__file__).resolve().parents[1]
        )
        schema = json.loads(
            (self.repo_root / "schema/result.schema.json").read_text(
                encoding="utf-8"
            )
        )
        Draft202012Validator.check_schema(schema)
        self._result_validator = Draft202012Validator(schema)

    @staticmethod
    def _error(exc: Exception) -> dict[str, str]:
        return {
            "type": type(exc).__name__,
            "message": str(exc),
        }

    @classmethod
    def _normalize_decision(cls, decision: Any) -> dict[str, Any]:
        if not isinstance(decision, dict):
            raise RunnerError("Policy act() must return an action dictionary")
        extra = set(decision) - cls.DECISION_KEYS
        if extra:
            raise RunnerError(
                "Policy decisions are semantic only; runner owns "
                f"episode_id/action_id. Unexpected keys: {sorted(extra)}"
            )
        action_type = decision.get("type")
        if not isinstance(action_type, str) or not action_type:
            raise RunnerError("Policy decision requires non-empty string type")
        supplier_id = decision.get("supplier_id")
        if supplier_id is not None and not isinstance(supplier_id, str):
            raise RunnerError("supplier_id must be a string or null")
        arguments = decision.get("arguments", {})
        if not isinstance(arguments, dict):
            raise RunnerError("arguments must be an object")
        return {
            "type": action_type,
            "supplier_id": supplier_id,
            "arguments": deepcopy(arguments),
        }

    @staticmethod
    def _policy_metadata(policy: AgentPolicy) -> dict[str, str]:
        policy_id = getattr(policy, "policy_id", None)
        policy_kind = getattr(policy, "policy_kind", None)
        if not isinstance(policy_id, str) or not policy_id:
            raise RunnerError("Policy requires non-empty policy_id")
        if not isinstance(policy_kind, str) or not policy_kind:
            raise RunnerError("Policy requires non-empty policy_kind")
        return {
            "policy_id": policy_id,
            "policy_kind": policy_kind,
        }

    def _build_result(
        self,
        *,
        run_id: str,
        episode_id: str,
        policy_meta: dict[str, str],
        status: str,
        max_actions: int,
        attempts: list[dict[str, Any]],
        trajectory: list[dict[str, Any]],
        evaluation: dict[str, Any] | None,
        error: dict[str, str] | None,
    ) -> dict[str, Any]:
        result = {
            "schema_version": self.RESULT_SCHEMA_VERSION,
            "benchmark": {
                "name": "LongProcureBench",
                "runner_version": self.RUNNER_VERSION,
            },
            "run_id": run_id,
            "episode_id": episode_id,
            "policy": policy_meta,
            "status": status,
            "max_actions": max_actions,
            "attempts": attempts,
            "trajectory": trajectory,
            "evaluation": evaluation,
            "error": error,
        }
        self._result_validator.validate(result)
        return result

    @staticmethod
    def save_result(result: dict[str, Any], path: str | Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return output

    def run(
        self,
        policy: AgentPolicy,
        episode_id: str,
        *,
        max_actions: int = 50,
        run_id: str | None = None,
        result_path: str | Path | None = None,
    ) -> dict[str, Any]:
        if not isinstance(max_actions, int) or isinstance(max_actions, bool) or max_actions < 1:
            raise RunnerError("max_actions must be a positive integer")

        policy_meta = self._policy_metadata(policy)
        resolved_run_id = run_id or (
            f"{policy_meta['policy_id']}--{episode_id}"
        )
        if not isinstance(resolved_run_id, str) or not resolved_run_id:
            raise RunnerError("run_id must be a non-empty string")

        attempts: list[dict[str, Any]] = []
        trajectory: list[dict[str, Any]] = []
        status = "completed"
        run_error: dict[str, str] | None = None
        evaluation: dict[str, Any] | None = None
        state: dict[str, Any] | None = None

        try:
            env = LongProcureBenchEnv(repo_root=self.repo_root)
            evaluator = LongProcureBenchEvaluator(repo_root=self.repo_root)
            state = env.reset(episode_id)
        except Exception as exc:
            status = "setup_error"
            run_error = self._error(exc)

        if state is not None:
            try:
                policy.reset(deepcopy(state))
            except Exception as exc:
                status = "policy_error"
                run_error = self._error(exc)

        while (
            status == "completed"
            and state is not None
            and not state["terminated"]
        ):
            if len(trajectory) >= max_actions:
                status = "max_actions"
                break

            attempt_number = len(attempts) + 1
            try:
                raw_decision = policy.act(deepcopy(state))
                decision = self._normalize_decision(raw_decision)
            except Exception as exc:
                status = "policy_error"
                run_error = self._error(exc)
                attempts.append(
                    {
                        "attempt": attempt_number,
                        "decision": None,
                        "accepted": False,
                        "error": deepcopy(run_error),
                    }
                )
                break

            action = {
                "action_id": f"a{len(trajectory) + 1}",
                "episode_id": episode_id,
                **decision,
            }
            attempt = {
                "attempt": attempt_number,
                "decision": deepcopy(decision),
                "accepted": False,
                "error": None,
            }
            try:
                state = env.step(action)
            except (ValidationError, EnvironmentError) as exc:
                status = "policy_error"
                run_error = self._error(exc)
                attempt["error"] = deepcopy(run_error)
                attempts.append(attempt)
                break
            except Exception as exc:
                status = "environment_error"
                run_error = self._error(exc)
                attempt["error"] = deepcopy(run_error)
                attempts.append(attempt)
                break

            attempt["accepted"] = True
            attempts.append(attempt)
            trajectory.append(
                {
                    "step": state["step"],
                    "action": deepcopy(action),
                    "observations": deepcopy(state["observations"]),
                }
            )

        if status != "setup_error":
            accepted_actions = [row["action"] for row in trajectory]
            try:
                evaluation = evaluator.evaluate_actions(
                    episode_id, accepted_actions
                )
            except Exception as exc:
                status = "evaluation_error"
                run_error = self._error(exc)

        result = self._build_result(
            run_id=resolved_run_id,
            episode_id=episode_id,
            policy_meta=policy_meta,
            status=status,
            max_actions=max_actions,
            attempts=attempts,
            trajectory=trajectory,
            evaluation=evaluation,
            error=run_error,
        )
        if result_path is not None:
            self.save_result(result, result_path)
        return result
