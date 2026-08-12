#!/usr/bin/env python3
"""Validate reviewed corporate-action resolutions against URL-backed evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


REQUIRED_EVIDENCE_FIELDS = {
    "evidence_id",
    "event_id",
    "symbol",
    "event_date",
    "source_type",
    "publisher",
    "source_url",
    "accessed_at",
    "facts",
    "evidence_quality",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_yaml(path: Path) -> dict[str, Any]:
    if yaml is None:  # pragma: no cover
        raise SystemExit("PyYAML is required to validate corporate-action evidence")
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a mapping")
    return payload


def validate_evidence_registry(evidence_payload: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    failures: list[str] = []
    rows = evidence_payload.get("evidence")
    if not isinstance(rows, list) or not rows:
        return {}, ["evidence must be a non-empty list"]
    by_id: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            failures.append(f"evidence[{index}] must be a mapping")
            continue
        missing = sorted(REQUIRED_EVIDENCE_FIELDS - set(row))
        if missing:
            failures.append(f"evidence[{index}] missing fields: {missing}")
        evidence_id = str(row.get("evidence_id") or "")
        if not evidence_id:
            failures.append(f"evidence[{index}] missing evidence_id")
        elif evidence_id in by_id:
            failures.append(f"duplicate evidence_id: {evidence_id}")
        else:
            by_id[evidence_id] = row
        url = str(row.get("source_url") or "")
        if not (url.startswith("https://") or url.startswith("http://")):
            failures.append(f"evidence[{index}] {evidence_id} source_url must be http(s)")
        for field in ("publisher", "accessed_at", "source_type", "evidence_quality", "symbol", "event_id", "event_date"):
            if not str(row.get(field) or "").strip():
                failures.append(f"evidence[{index}] {evidence_id} missing {field}")
        facts = row.get("facts")
        if not isinstance(facts, dict) or not facts:
            failures.append(f"evidence[{index}] {evidence_id} facts must be a non-empty mapping")
    return by_id, failures


def validate_resolutions(resolution_payload: dict[str, Any], evidence_by_id: dict[str, dict[str, Any]]) -> list[str]:
    failures: list[str] = []
    rows = resolution_payload.get("resolutions")
    if not isinstance(rows, list):
        return ["resolutions must be a list"]
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            failures.append(f"resolution[{index}] must be a mapping")
            continue
        if row.get("review_status") != "APPROVED":
            continue
        event_id = str(row.get("event_id") or "")
        symbol = str(row.get("symbol") or "")
        refs = row.get("evidence_references")
        if not isinstance(refs, list) or not refs:
            failures.append(f"resolution[{index}] {event_id} needs evidence_references")
            continue
        for ref in refs:
            evidence = evidence_by_id.get(str(ref))
            if evidence is None:
                failures.append(f"resolution[{index}] {event_id} unknown evidence ID: {ref}")
                continue
            if str(evidence.get("event_id")) != event_id:
                failures.append(f"resolution[{index}] {event_id} evidence {ref} event_id mismatch: {evidence.get('event_id')}")
            if str(evidence.get("symbol")) != symbol:
                failures.append(f"resolution[{index}] {event_id} evidence {ref} symbol mismatch: {evidence.get('symbol')}")
            if not str(evidence.get("publisher") or "").strip():
                failures.append(f"resolution[{index}] {event_id} evidence {ref} missing publisher")
            if not str(evidence.get("accessed_at") or "").strip():
                failures.append(f"resolution[{index}] {event_id} evidence {ref} missing accessed_at")
            if not str(evidence.get("evidence_quality") or "").strip():
                failures.append(f"resolution[{index}] {event_id} evidence {ref} missing evidence_quality")
            url = str(evidence.get("source_url") or "")
            if not (url.startswith("https://") or url.startswith("http://")):
                failures.append(f"resolution[{index}] {event_id} evidence {ref} missing URL")
            if not isinstance(evidence.get("facts"), dict) or not evidence.get("facts"):
                failures.append(f"resolution[{index}] {event_id} evidence {ref} missing facts")
    return failures


def evidence_audit(
    resolutions_path: Path,
    evidence_path: Path,
    *,
    report_path: Path | None = None,
) -> dict[str, Any]:
    resolutions = load_yaml(resolutions_path)
    evidence = load_yaml(evidence_path)
    evidence_by_id, evidence_failures = validate_evidence_registry(evidence)
    resolution_failures = validate_resolutions(resolutions, evidence_by_id)
    approved = [row for row in resolutions.get("resolutions", []) if isinstance(row, dict) and row.get("review_status") == "APPROVED"]
    referenced = {str(ref) for row in approved for ref in (row.get("evidence_references") or [])}
    unresolved = sorted(ref for ref in referenced if ref not in evidence_by_id)
    missing_url_count = sum(1 for row in evidence_by_id.values() if not str(row.get("source_url") or "").startswith(("http://", "https://")))
    quality_counts: dict[str, int] = {}
    for row in evidence_by_id.values():
        quality = str(row.get("evidence_quality") or "MISSING")
        quality_counts[quality] = quality_counts.get(quality, 0) + 1
    failures = evidence_failures + resolution_failures
    summary = {
        "status": "PASS" if not failures else "FAIL",
        "reviewed_resolution_count": len(approved),
        "evidence_entry_count": len(evidence_by_id),
        "referenced_evidence_count": len(referenced),
        "missing_url_count": missing_url_count,
        "unresolved_evidence_id_count": len(unresolved),
        "unresolved_evidence_ids": unresolved,
        "evidence_quality_counts": quality_counts,
        "corporate_action_resolution_sha256": sha256(resolutions_path),
        "corporate_action_evidence_sha256": sha256(evidence_path),
        "failures": failures,
    }
    if report_path is not None:
        lines = [
            "# Corporate-action evidence audit",
            "",
            f"Reviewed events: `{len(approved)}`.",
            f"Evidence entries: `{len(evidence_by_id)}`.",
            f"Missing URL count: `{missing_url_count}`.",
            f"Unresolved evidence IDs: `{len(unresolved)}`.",
            f"Resolution hash: `{summary['corporate_action_resolution_sha256']}`.",
            f"Evidence registry hash: `{summary['corporate_action_evidence_sha256']}`.",
            f"Status: `{summary['status']}`.",
            "",
            "## Evidence quality counts",
            "",
            "| Quality | Count |",
            "|---|---:|",
        ]
        lines.extend(f"| `{quality}` | {count} |" for quality, count in sorted(quality_counts.items()))
        lines.extend([
            "",
            "## Reviewed resolution evidence",
            "",
            "| Event | Symbol | References |",
            "|---|---|---|",
        ])
        for row in approved:
            lines.append(f"| `{row.get('event_id')}` | `{row.get('symbol')}` | {', '.join(row.get('evidence_references') or [])} |")
        if failures:
            lines.extend(["", "## Failures", ""])
            lines.extend(f"- {failure}" for failure in failures)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resolutions", default="data/reference/corporate_action_resolutions.yaml")
    parser.add_argument("--evidence", default="data/reference/corporate_action_evidence.yaml")
    parser.add_argument("--report")
    args = parser.parse_args()
    summary = evidence_audit(
        Path(args.resolutions),
        Path(args.evidence),
        report_path=Path(args.report) if args.report else None,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    if summary["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
