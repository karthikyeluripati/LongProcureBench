"""Independently reproduce frozen working-plan compaction from the Actions artifact."""
from __future__ import annotations

import argparse
import base64
import gzip
from hashlib import sha256
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
from frozen_working_plan_v01 import (
    EPISODES, EXPECTED_COMPACTION_SHA256, EXPECTED_COMPRESSED_BYTES,
    EXPECTED_COMPRESSED_SHA256, EXPECTED_PROVENANCE_BYTES,
    EXPECTED_PROVENANCE_SHA256, EXPECTED_RAW_PROVENANCE_SHA256,
)

EXPECTED_ARTIFACT_SHA256 = "924443c9bde20b687a2a3b9fe0c8058f8a224604d8532d6c325c6a9c89fd6c9b"
EXPECTED_ARTIFACT_BYTES = 280188


def canonical(row):
    return json.dumps(row, separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\n"


def compact(payload, episode_index, repeat):
    run = json.loads(payload)
    pm = run["policy_metrics"]
    decisions = [[a["decision"]["type"], a["decision"].get("supplier_id"), a["decision"].get("arguments") or {}] for a in run["attempts"] if a.get("accepted")]
    metrics = [pm["model_calls_attempted"], pm["prompt_tokens"], pm["completion_tokens"], pm["total_tokens"], pm["latency_ms"], pm["cost_usd"], pm["usage_incomplete"], pm.get("temperature"), pm.get("reasoning_effort"), pm.get("context_strategy"), pm.get("state_strategy"), pm.get("plan_updates"), pm.get("plan_rejections"), pm.get("mean_plan_steps"), pm.get("max_plan_steps")]
    return [episode_index, repeat, run["status"], decisions, metrics, pm.get("final_plan"), pm.get("plan_trace") or [], pm.get("plan_rejection_trace") or []]


def root(lines):
    return sha256(("\n".join(lines) + "\n").encode("utf-8")).hexdigest()


def verify_artifact(path: Path, replay_output: Path | None = None):
    blob = path.read_bytes()
    if len(blob) != EXPECTED_ARTIFACT_BYTES or sha256(blob).hexdigest() != EXPECTED_ARTIFACT_SHA256:
        raise ValueError("Working-plan artifact ZIP digest/size mismatch")
    rows = []; provenance = []; raw_lines = []
    with zipfile.ZipFile(path) as zf:
        entries = [name for name in zf.namelist() if name.endswith('.json') and '/run-' in name]
        parsed = []
        for name in entries:
            raw = zf.read(name); run = json.loads(raw)
            episode_id = run.get("episode_id")
            if episode_id not in EPISODES: raise ValueError(f"Unexpected episode in artifact: {episode_id}")
            repeat = int(Path(name).stem.rsplit('-', 1)[1]); parsed.append((EPISODES.index(episode_id)+1, repeat, raw))
        parsed.sort()
        if len(parsed) != 60: raise ValueError(f"Expected 60 run JSON files; found {len(parsed)}")
        for episode_index, repeat, raw in parsed:
            row = compact(raw, episode_index, repeat); rows.append(row)
            raw_sha = sha256(raw).hexdigest(); compact_sha = sha256(canonical(row)).hexdigest()
            provenance.append(f"{episode_index}|{repeat}|{raw_sha}|{compact_sha}")
            raw_lines.append(f"{episode_index}|{repeat}|{raw_sha}")
    payload = b"".join(canonical(row) for row in rows)
    if sha256(payload).hexdigest() != EXPECTED_COMPACTION_SHA256: raise ValueError("Artifact-derived compaction digest mismatch")
    if root(raw_lines) != EXPECTED_RAW_PROVENANCE_SHA256: raise ValueError("Artifact-derived raw provenance root mismatch")
    committed = (ROOT / 'evidence' / 'working-plan-reactive-v0.1' / 'source-provenance.txt').read_bytes()
    expected_prov = ('\n'.join(provenance) + '\n').encode()
    if len(committed) != EXPECTED_PROVENANCE_BYTES or sha256(committed).hexdigest() != EXPECTED_PROVENANCE_SHA256 or committed != expected_prov:
        raise ValueError("Committed working-plan provenance does not match artifact-derived records")
    compressed = gzip.compress(payload, compresslevel=9, mtime=0)
    if len(compressed) != EXPECTED_COMPRESSED_BYTES or sha256(compressed).hexdigest() != EXPECTED_COMPRESSED_SHA256: raise ValueError("Regenerated replay source mismatch")
    if replay_output is not None:
        replay_output.write_text(base64.b64encode(compressed).decode('ascii') + '\n', encoding='utf-8')
    return {"artifact_sha256": EXPECTED_ARTIFACT_SHA256, "compaction_sha256": EXPECTED_COMPACTION_SHA256, "raw_provenance_sha256": EXPECTED_RAW_PROVENANCE_SHA256}


def main():
    p = argparse.ArgumentParser(); p.add_argument('--artifact-zip', required=True); p.add_argument('--write-replay-source'); a = p.parse_args()
    print(json.dumps(verify_artifact(Path(a.artifact_zip), Path(a.write_replay_source) if a.write_replay_source else None), indent=2, sort_keys=True))

if __name__ == '__main__': main()
