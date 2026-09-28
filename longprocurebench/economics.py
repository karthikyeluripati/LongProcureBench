"""Deterministic procurement economics for ProcureHarness experiments.

This module is intentionally additive to Evaluator v0.2. It consumes a
standardized LongProcureBench result plus the frozen episode/oracle data and
derives scope-aware award cost, feasible price regret, and matched-cohort
savings without changing benchmark success semantics.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping
import hashlib
import json
import math


QUOTE_TYPES = {"quote_received", "quote_revision"}


class EconomicsError(ValueError):
    """Raised when benchmark economics data or reports are inconsistent."""


def _is_number(value: Any) -> bool:
    """Return True only for finite JSON-safe numeric values."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except (OverflowError, ValueError):
        return False


def _canonical_json_bytes(value: Any) -> bytes:
    """Canonical JSON bytes; reject NaN/Infinity instead of emitting them."""
    try:
        text = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise EconomicsError(
            "Economics report contains non-JSON or non-finite data"
        ) from exc
    return text.encode("utf-8")


def _reports_sha256(
    reports: Mapping[tuple[str, int], Mapping[str, Any]],
) -> str:
    payload = [
        reports[key]
        for key in sorted(reports)
    ]
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _safe_percent(
    numerator: float,
    denominator: float,
    *,
    label: str,
) -> float:
    """Compute 100 * numerator / denominator without intermediate overflow."""
    if not _is_number(numerator) or not _is_number(denominator):
        raise EconomicsError(f"{label} inputs must be finite numeric values")
    denominator_f = float(denominator)
    if denominator_f == 0:
        raise EconomicsError(f"{label} denominator must be non-zero")

    ratio = float(numerator) / denominator_f
    if not math.isfinite(ratio):
        raise EconomicsError(f"{label} ratio is non-finite")

    percent = ratio * 100.0
    if not math.isfinite(percent):
        raise EconomicsError(f"{label} percent is non-finite")
    return percent


def _finite_mean(values: Iterable[float], *, label: str) -> float:
    numeric = [float(value) for value in values]
    if not numeric:
        raise EconomicsError(f"{label} requires at least one value")
    if not all(math.isfinite(value) for value in numeric):
        raise EconomicsError(f"{label} contains non-finite values")
    try:
        total = math.fsum(numeric)
    except OverflowError as exc:
        raise EconomicsError(
            f"{label} accumulation overflowed"
        ) from exc
    if not math.isfinite(total):
        raise EconomicsError(f"{label} accumulation is non-finite")
    mean = total / len(numeric)
    if not math.isfinite(mean):
        raise EconomicsError(f"{label} mean is non-finite")
    return mean


def normalize_regret(
    selected_cost: float,
    oracle_cost: float,
) -> tuple[float | None, str]:
    """Return normalized regret percent and its normalization status."""
    if not _is_number(selected_cost) or not _is_number(oracle_cost):
        raise EconomicsError("selected_cost and oracle_cost must be numeric")
    if selected_cost < 0 or oracle_cost < 0:
        raise EconomicsError("selected_cost and oracle_cost must be non-negative")

    if oracle_cost == 0:
        return None, "not_normalizable_zero_oracle"

    regret = max(0.0, float(selected_cost) - float(oracle_cost))
    return (
        _safe_percent(
            regret,
            float(oracle_cost),
            label="feasible price regret",
        ),
        "normalizable",
    )


def _run_key(report: Mapping[str, Any]) -> tuple[str, int]:
    run_key = report.get("run_key")
    if not isinstance(run_key, Mapping):
        raise EconomicsError("Economics report is missing run_key")
    episode_id = run_key.get("episode_id")
    repeat = run_key.get("repeat")
    if not isinstance(episode_id, str) or not episode_id:
        raise EconomicsError("run_key.episode_id must be a non-empty string")
    if not isinstance(repeat, int) or isinstance(repeat, bool) or repeat < 1:
        raise EconomicsError("run_key.repeat must be a positive integer")
    return episode_id, repeat


def _index_reports(
    reports: Iterable[Mapping[str, Any]],
    *,
    label: str,
) -> dict[tuple[str, int], Mapping[str, Any]]:
    out: dict[tuple[str, int], Mapping[str, Any]] = {}
    for report in reports:
        key = _run_key(report)
        if key in out:
            raise EconomicsError(f"Duplicate {label} economics run key: {key}")
        out[key] = report
    return out


class EconomicRegretEvaluator:
    """Score standardized benchmark results under economics protocol v0.1."""

    SCHEMA_VERSION = "0.1.0"
    ECONOMICS_VERSION = "0.1.0"

    def __init__(self, repo_root: str | Path | None = None):
        self.repo_root = (
            Path(repo_root).resolve()
            if repo_root is not None
            else Path(__file__).resolve().parents[1]
        )

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _load_episode(self, episode_id: str) -> dict[str, Any]:
        path = (
            self.repo_root
            / "data"
            / "episodes"
            / "electrical"
            / f"{episode_id}.json"
        )
        if not path.is_file():
            raise EconomicsError(f"Missing episode for economics: {episode_id}")
        episode = self._read_json(path)
        if episode.get("episode_id") != episode_id:
            raise EconomicsError("Economics episode_id mismatch")
        return episode

    def _initial_item_ids(self, episode: Mapping[str, Any]) -> set[str]:
        ref = episode.get("initial_state_ref") or {}
        rel = ref.get("path")
        if not isinstance(rel, str) or not rel:
            raise EconomicsError("Episode is missing initial_state_ref.path")
        initial_path = self.repo_root / rel
        if not initial_path.is_file():
            raise EconomicsError(
                f"Missing initial state for economics: {initial_path}"
            )
        initial = self._read_json(initial_path)
        items = initial.get("line_items")
        if not isinstance(items, list) or not items:
            raise EconomicsError("Initial state has no line items")
        item_ids = {
            item.get("item_id")
            for item in items
            if isinstance(item, Mapping)
        }
        if None in item_ids or any(
            not isinstance(item_id, str) or not item_id
            for item_id in item_ids
        ):
            raise EconomicsError("Initial state contains invalid item_id")
        return set(item_ids)

    @staticmethod
    def _required_items(scope: str, initial_item_ids: set[str]) -> set[str]:
        if scope == "package":
            return set(initial_item_ids)
        if scope.startswith("lot-"):
            item_id = scope[len("lot-") :]
            if item_id not in initial_item_ids:
                raise EconomicsError(
                    f"Award scope references unknown item: {scope}"
                )
            return {item_id}
        raise EconomicsError(f"Unsupported award scope: {scope}")

    @staticmethod
    def _covered_items(
        event: Mapping[str, Any],
        initial_item_ids: set[str],
    ) -> set[str]:
        scope = event.get("offer_scope")
        if not isinstance(scope, Mapping):
            raise EconomicsError(
                f"Quote event {event.get('event_id')} missing offer_scope"
            )
        kind = scope.get("kind")
        if kind == "package":
            return set(initial_item_ids)
        if kind == "items":
            values = scope.get("item_ids")
            if not isinstance(values, list):
                raise EconomicsError("items offer_scope requires item_ids")
            item_ids = set(values)
            unknown = item_ids - initial_item_ids
            if unknown:
                raise EconomicsError(
                    f"Quote event covers unknown items: {sorted(unknown)}"
                )
            return item_ids
        raise EconomicsError(f"Unsupported offer_scope kind: {kind!r}")

    @classmethod
    def _award_price_and_currency(
        cls,
        award: Mapping[str, Any],
        event: Mapping[str, Any],
        initial_item_ids: set[str],
    ) -> tuple[float, str]:
        if event.get("type") not in QUOTE_TYPES:
            raise EconomicsError(
                f"Award references non-quote event: {event.get('event_id')}"
            )
        if event.get("supplier_id") != award.get("supplier_id"):
            raise EconomicsError(
                "Award supplier does not match referenced quote supplier"
            )

        scope = award.get("scope")
        if not isinstance(scope, str):
            raise EconomicsError("Award scope must be a string")

        required = cls._required_items(scope, initial_item_ids)
        covered = cls._covered_items(event, initial_item_ids)
        if not required.issubset(covered):
            raise EconomicsError(
                f"Quote {event.get('event_id')} does not cover award scope "
                f"{scope}"
            )

        details = event.get("details")
        if not isinstance(details, Mapping):
            raise EconomicsError("Quote event is missing details")

        if scope == "package":
            price = details.get("total_price")
        else:
            item_id = scope[len("lot-") :]
            lots = details.get("lots")
            lot = lots.get(item_id) if isinstance(lots, Mapping) else None
            price = lot.get("price") if isinstance(lot, Mapping) else None

        if not _is_number(price):
            raise EconomicsError(
                f"Missing or non-finite numeric award price for "
                f"{event.get('event_id')} scope {scope}"
            )
        if float(price) < 0:
            raise EconomicsError("Award price must be non-negative")

        currency = details.get("currency")
        if not isinstance(currency, str) or not currency:
            raise EconomicsError(
                f"Missing quote currency for {event.get('event_id')}"
            )
        return float(price), currency

    def _outcome_cost(
        self,
        episode: Mapping[str, Any],
        outcome: Mapping[str, Any],
    ) -> tuple[float, str]:
        if outcome.get("decision") != "award":
            raise EconomicsError("Price economics require an award outcome")

        events = episode.get("events")
        if not isinstance(events, list):
            raise EconomicsError("Episode events must be a list")
        by_event = {
            event.get("event_id"): event
            for event in events
            if isinstance(event, Mapping)
        }
        initial_item_ids = self._initial_item_ids(episode)

        awards = outcome.get("awards")
        if not isinstance(awards, list) or not awards:
            raise EconomicsError("Award outcome must contain awards")

        total = 0.0
        currencies: set[str] = set()
        for award in awards:
            if not isinstance(award, Mapping):
                raise EconomicsError("Award must be an object")
            event_id = award.get("quote_event_id")
            event = by_event.get(event_id)
            if not isinstance(event, Mapping):
                raise EconomicsError(
                    f"Award references missing quote event: {event_id}"
                )
            price, currency = self._award_price_and_currency(
                award,
                event,
                initial_item_ids,
            )
            total += price
            if not math.isfinite(total):
                raise EconomicsError(
                    "Summed award cost is non-finite"
                )
            currencies.add(currency)

        if len(currencies) != 1:
            raise EconomicsError(
                "One outcome cannot mix native quote currencies"
            )
        return total, next(iter(currencies))

    @staticmethod
    def _outcomes_by_id(
        episode: Mapping[str, Any],
    ) -> dict[str, Mapping[str, Any]]:
        oracle = episode.get("oracle")
        if not isinstance(oracle, Mapping):
            raise EconomicsError("Episode is missing oracle")
        outcomes = oracle.get("acceptable_terminal_outcomes")
        if not isinstance(outcomes, list):
            raise EconomicsError("Episode is missing acceptable outcomes")
        out: dict[str, Mapping[str, Any]] = {}
        for outcome in outcomes:
            if not isinstance(outcome, Mapping):
                raise EconomicsError("Acceptable outcome must be an object")
            outcome_id = outcome.get("outcome_id")
            if not isinstance(outcome_id, str) or not outcome_id:
                raise EconomicsError("Acceptable outcome requires outcome_id")
            if outcome_id in out:
                raise EconomicsError(f"Duplicate outcome id: {outcome_id}")
            out[outcome_id] = outcome
        return out

    def _oracle_cost(
        self,
        episode: Mapping[str, Any],
        outcomes: Mapping[str, Mapping[str, Any]],
    ) -> tuple[float, str]:
        objective = episode["oracle"].get("economic_objective")
        if not isinstance(objective, Mapping):
            raise EconomicsError("Episode is missing economic objective")
        if objective.get("kind") != "minimize_total_price":
            raise EconomicsError(
                f"Unsupported economic objective: {objective.get('kind')}"
            )

        preferred = objective.get("preferred_outcome_ids")
        if not isinstance(preferred, list) or not preferred:
            raise EconomicsError("Economic objective has no preferred outcomes")

        costs: list[tuple[float, str]] = []
        for outcome_id in preferred:
            outcome = outcomes.get(outcome_id)
            if outcome is None:
                raise EconomicsError(
                    f"Preferred outcome not found: {outcome_id}"
                )
            if outcome.get("decision") != "award":
                raise EconomicsError(
                    "No-award preferred outcomes are not price-regret eligible"
                )
            costs.append(self._outcome_cost(episode, outcome))

        currencies = {currency for _, currency in costs}
        if len(currencies) != 1:
            raise EconomicsError(
                "Preferred outcomes do not share one native currency"
            )
        return min(cost for cost, _ in costs), next(iter(currencies))

    @staticmethod
    def _base_report(
        result: Mapping[str, Any],
        *,
        repeat: int,
    ) -> dict[str, Any]:
        episode_id = result.get("episode_id")
        if not isinstance(episode_id, str) or not episode_id:
            raise EconomicsError("Result requires episode_id")
        if not isinstance(repeat, int) or isinstance(repeat, bool) or repeat < 1:
            raise EconomicsError("repeat must be a positive integer")
        return {
            "schema_version": EconomicRegretEvaluator.SCHEMA_VERSION,
            "economics_version": EconomicRegretEvaluator.ECONOMICS_VERSION,
            "episode_id": episode_id,
            "repeat": repeat,
            "run_key": {
                "episode_id": episode_id,
                "repeat": repeat,
            },
            "run_id": result.get("run_id"),
            "policy_id": (
                result.get("policy", {}).get("policy_id")
                if isinstance(result.get("policy"), Mapping)
                else None
            ),
            "eligible": False,
            "eligibility_reason": None,
            "currency": None,
            "selected_outcome_id": None,
            "selected_cost_native": None,
            "oracle_cost_native": None,
            "feasible_price_regret_native": None,
            "feasible_price_regret_pct": None,
            "normalized_regret_status": "not_eligible",
        }

    def score_result(
        self,
        result: Mapping[str, Any],
        *,
        repeat: int,
    ) -> dict[str, Any]:
        """Compute per-run economics from a standardized benchmark result."""
        report = self._base_report(result, repeat=repeat)
        evaluation = result.get("evaluation")
        if not isinstance(evaluation, Mapping):
            report["eligibility_reason"] = "missing_evaluation"
            return report
        if evaluation.get("episode_id") != report["episode_id"]:
            raise EconomicsError(
                "Result episode_id does not match evaluation episode_id"
            )

        objective = evaluation.get("economic_objective")
        if (
            not isinstance(objective, Mapping)
            or objective.get("kind") != "minimize_total_price"
        ):
            report["eligibility_reason"] = "unsupported_economic_objective"
            return report

        terminal = evaluation.get("terminal_outcome")
        if not isinstance(terminal, Mapping) or terminal.get("correct") is not True:
            report["eligibility_reason"] = "terminal_not_feasible"
            return report

        hard = evaluation.get("hard_constraints")
        if not isinstance(hard, Mapping) or hard.get("all_passed") is not True:
            report["eligibility_reason"] = "hard_constraints_failed"
            return report

        matched_outcome_id = terminal.get("matched_outcome_id")
        if not isinstance(matched_outcome_id, str) or not matched_outcome_id:
            report["eligibility_reason"] = "missing_matched_outcome"
            return report

        episode = self._load_episode(report["episode_id"])
        outcomes = self._outcomes_by_id(episode)
        matched = outcomes.get(matched_outcome_id)
        if matched is None:
            raise EconomicsError(
                f"Matched outcome missing from episode: {matched_outcome_id}"
            )
        report["selected_outcome_id"] = matched_outcome_id

        if matched.get("decision") != "award":
            report["eligibility_reason"] = "no_award_outcome"
            return report

        selected_cost, selected_currency = self._outcome_cost(
            episode,
            matched,
        )
        oracle_cost, oracle_currency = self._oracle_cost(episode, outcomes)
        if selected_currency != oracle_currency:
            raise EconomicsError(
                "Selected and oracle outcomes use different currencies"
            )

        regret = max(0.0, selected_cost - oracle_cost)
        regret_pct, normalization_status = normalize_regret(
            selected_cost,
            oracle_cost,
        )

        report.update(
            {
                "eligible": True,
                "eligibility_reason": "eligible",
                "currency": selected_currency,
                "selected_cost_native": selected_cost,
                "oracle_cost_native": oracle_cost,
                "feasible_price_regret_native": regret,
                "feasible_price_regret_pct": regret_pct,
                "normalized_regret_status": normalization_status,
            }
        )
        return report


def freeze_reference_cohort(
    coverage_repair_reports: Iterable[Mapping[str, Any]],
    react_reports: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Freeze the positive-oracle-cost matched regret cohort."""
    coverage = _index_reports(
        coverage_repair_reports,
        label="Coverage+Repair",
    )
    react = _index_reports(react_reports, label="ReAct")

    coverage_keys = set(coverage)
    react_keys = set(react)
    if coverage_keys != react_keys:
        missing_from_coverage = sorted(react_keys - coverage_keys)
        missing_from_react = sorted(coverage_keys - react_keys)
        raise EconomicsError(
            "Matched baseline economics grids differ: "
            f"missing_from_coverage={missing_from_coverage}, "
            f"missing_from_react={missing_from_react}"
        )

    shared = sorted(coverage_keys)
    positive_keys: list[tuple[str, int]] = []
    joint_eligible = 0
    zero_oracle = 0

    for key in shared:
        left = coverage[key]
        right = react[key]
        if left.get("eligible") is not True or right.get("eligible") is not True:
            continue
        joint_eligible += 1

        if left.get("currency") != right.get("currency"):
            raise EconomicsError(
                f"Baseline currency mismatch on run key {key}"
            )
        left_oracle = left.get("oracle_cost_native")
        right_oracle = right.get("oracle_cost_native")
        if not _is_number(left_oracle) or not _is_number(right_oracle):
            raise EconomicsError(
                f"Eligible baseline report missing oracle cost on {key}"
            )
        if not math.isclose(
            float(left_oracle),
            float(right_oracle),
            rel_tol=1e-12,
            abs_tol=1e-9,
        ):
            raise EconomicsError(
                f"Baseline oracle cost mismatch on run key {key}"
            )
        if float(left_oracle) < 0:
            raise EconomicsError("Oracle cost must be non-negative")

        if float(left_oracle) == 0:
            zero_oracle += 1
            continue

        for label, row in (
            ("Coverage+Repair", left),
            ("ReAct", right),
        ):
            if row.get("normalized_regret_status") != "normalizable":
                raise EconomicsError(
                    f"{label} positive-oracle row is not normalizable on {key}"
                )
            if not _is_number(row.get("feasible_price_regret_pct")):
                raise EconomicsError(
                    f"{label} positive-oracle row missing regret percent on {key}"
                )
        positive_keys.append(key)

    status = (
        "available"
        if positive_keys
        else "unavailable_empty_reference_cohort"
    )
    return {
        "schema_version": "0.1.0",
        "status": status,
        "reference_cohort_count": len(positive_keys),
        "joint_regret_eligible_count": joint_eligible,
        "zero_oracle_cost_run_count_outside_percentage_reference_cohort": (
            zero_oracle
        ),
        "run_keys": [
            {"episode_id": episode_id, "repeat": repeat}
            for episode_id, repeat in positive_keys
        ],
        "baseline_report_bindings": {
            "hash_algorithm": "sha256",
            "canonicalization": "json-sort-keys-compact-allow-nan-false-v1",
            "coverage_repair_reports_sha256": _reports_sha256(coverage),
            "react_reports_sha256": _reports_sha256(react),
            "coverage_repair_report_count": len(coverage),
            "react_report_count": len(react),
        },
    }


def compare_candidate_on_reference_cohort(
    candidate_reports: Iterable[Mapping[str, Any]],
    *,
    coverage_repair_reports: Iterable[Mapping[str, Any]],
    react_reports: Iterable[Mapping[str, Any]],
    reference_cohort: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compare one candidate with matched baselines on one frozen cohort."""
    candidate = _index_reports(candidate_reports, label="candidate")
    coverage = _index_reports(
        coverage_repair_reports,
        label="Coverage+Repair",
    )
    react = _index_reports(react_reports, label="ReAct")
    expected_cohort = freeze_reference_cohort(
        coverage.values(),
        react.values(),
    )
    if reference_cohort is not None:
        supplied = dict(reference_cohort)
        if supplied != expected_cohort:
            raise EconomicsError(
                "Supplied reference cohort does not match baseline-derived cohort"
            )
    cohort = expected_cohort

    raw_keys = cohort.get("run_keys")
    if not isinstance(raw_keys, list):
        raise EconomicsError("Reference cohort requires run_keys")
    keys: list[tuple[str, int]] = []
    for row in raw_keys:
        if not isinstance(row, Mapping):
            raise EconomicsError("Reference cohort run_key must be an object")
        keys.append(
            _run_key(
                {
                    "run_key": {
                        "episode_id": row.get("episode_id"),
                        "repeat": row.get("repeat"),
                    }
                }
            )
        )

    if len(keys) != len(set(keys)):
        raise EconomicsError("Reference cohort contains duplicate run keys")

    cohort_count = len(keys)
    declared_count = cohort.get("reference_cohort_count")
    if declared_count != cohort_count:
        raise EconomicsError(
            "Reference cohort count does not match run_keys"
        )
    cohort_status = cohort.get("status")
    if cohort_count == 0 and cohort_status != (
        "unavailable_empty_reference_cohort"
    ):
        raise EconomicsError("Empty reference cohort status mismatch")
    if cohort_count > 0 and cohort_status != "available":
        raise EconomicsError("Non-empty reference cohort status mismatch")
    if cohort_count == 0:
        return {
            "schema_version": "0.1.0",
            "status": "unavailable_empty_reference_cohort",
            "reference_cohort_count": 0,
            "candidate_regret_eligible_count_on_reference_cohort": 0,
            "candidate_regret_eligibility_rate_on_reference_cohort": None,
            "mean_feasible_price_regret_pct_on_reference_cohort": None,
            "regret_comparable": False,
            "paired_savings": {
                "coverage_repair": {
                    "status": "unavailable_empty_reference_cohort"
                },
                "react": {
                    "status": "unavailable_empty_reference_cohort"
                },
            },
        }

    eligible_count = 0
    comparable_rows: list[Mapping[str, Any]] = []
    for key in keys:
        row = candidate.get(key)
        if (
            row is not None
            and row.get("eligible") is True
            and row.get("normalized_regret_status") == "normalizable"
            and _is_number(row.get("feasible_price_regret_pct"))
        ):
            eligible_count += 1
            comparable_rows.append(row)

    rate = eligible_count / cohort_count
    if eligible_count != cohort_count:
        return {
            "schema_version": "0.1.0",
            "status": "not_comparable_incomplete_candidate_cohort",
            "reference_cohort_count": cohort_count,
            "candidate_regret_eligible_count_on_reference_cohort": (
                eligible_count
            ),
            "candidate_regret_eligibility_rate_on_reference_cohort": rate,
            "mean_feasible_price_regret_pct_on_reference_cohort": None,
            "regret_comparable": False,
            "paired_savings": None,
        }

    regret_values = [
        float(row["feasible_price_regret_pct"])
        for row in comparable_rows
    ]
    try:
        regret_sum = math.fsum(regret_values)
    except OverflowError as exc:
        raise EconomicsError(
            "Mean regret accumulation overflowed"
        ) from exc
    if not math.isfinite(regret_sum):
        raise EconomicsError("Mean regret accumulation is non-finite")
    mean_regret = regret_sum / cohort_count
    if not math.isfinite(mean_regret):
        raise EconomicsError("Mean regret is non-finite")

    def paired(
        baseline: Mapping[tuple[str, int], Mapping[str, Any]],
        label: str,
    ) -> dict[str, Any]:
        pairs = []
        by_currency: dict[str, dict[str, Any]] = {}
        pct_values = []

        for key in keys:
            cand = candidate[key]
            base = baseline.get(key)
            if base is None or base.get("eligible") is not True:
                raise EconomicsError(
                    f"{label} baseline missing eligible cohort row: {key}"
                )

            if cand.get("currency") != base.get("currency"):
                raise EconomicsError(
                    f"{label} candidate/baseline currency mismatch on {key}"
                )

            cand_oracle = cand.get("oracle_cost_native")
            base_oracle = base.get("oracle_cost_native")
            if not _is_number(cand_oracle) or not _is_number(base_oracle):
                raise EconomicsError(
                    f"{label} missing oracle cost on {key}"
                )
            if not math.isclose(
                float(cand_oracle),
                float(base_oracle),
                rel_tol=1e-12,
                abs_tol=1e-9,
            ):
                raise EconomicsError(
                    f"{label} candidate/baseline oracle mismatch on {key}"
                )

            cand_cost = cand.get("selected_cost_native")
            base_cost = base.get("selected_cost_native")
            if not _is_number(cand_cost) or not _is_number(base_cost):
                raise EconomicsError(
                    f"{label} missing selected cost on {key}"
                )

            savings = float(base_cost) - float(cand_cost)
            if float(base_cost) > 0:
                savings_pct = _safe_percent(
                    savings,
                    float(base_cost),
                    label=f"{label} paired savings",
                )
                savings_pct_status = "normalizable"
                pct_values.append(savings_pct)
            else:
                savings_pct = None
                savings_pct_status = "not_normalizable_zero_baseline"

            currency = str(cand["currency"])
            bucket = by_currency.setdefault(
                currency,
                {
                    "pairs": 0,
                    "sum_paired_savings_native": 0.0,
                },
            )
            bucket["pairs"] += 1
            bucket["sum_paired_savings_native"] += savings
            if not math.isfinite(bucket["sum_paired_savings_native"]):
                raise EconomicsError(
                    f"{label} native savings accumulation is non-finite"
                )

            pairs.append(
                {
                    "run_key": {
                        "episode_id": key[0],
                        "repeat": key[1],
                    },
                    "currency": currency,
                    "baseline_selected_cost_native": float(base_cost),
                    "candidate_selected_cost_native": float(cand_cost),
                    "paired_savings_native": savings,
                    "paired_savings_pct": savings_pct,
                    "paired_savings_pct_status": savings_pct_status,
                }
            )

        return {
            "status": "available",
            "pairs": pairs,
            "native_savings_by_currency": by_currency,
            "mean_paired_savings_pct": (
                _finite_mean(
                    pct_values,
                    label=f"{label} paired savings percent",
                )
                if pct_values
                else None
            ),
        }

    return {
        "schema_version": "0.1.0",
        "status": "comparable",
        "reference_cohort_count": cohort_count,
        "candidate_regret_eligible_count_on_reference_cohort": eligible_count,
        "candidate_regret_eligibility_rate_on_reference_cohort": rate,
        "mean_feasible_price_regret_pct_on_reference_cohort": mean_regret,
        "regret_comparable": True,
        "paired_savings": {
            "coverage_repair": paired(coverage, "Coverage+Repair"),
            "react": paired(react, "ReAct"),
        },
    }
