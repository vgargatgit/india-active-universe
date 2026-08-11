#!/usr/bin/env python3
"""Fail if code couples this data project to strategy or index-membership work."""

from __future__ import annotations

import json
import re
from pathlib import Path


CHECK_ROOTS = (".github", "scripts", "src", "tests")
TEXT_SUFFIXES = {".py", ".yml", ".yaml", ".toml"}
FORBIDDEN_TEXT = (
    "india500-alpha-lab",
    "NIFTY500",
    "NIFTY 500",
)
FORBIDDEN_PATH_PATTERNS = (
    re.compile(r"(^|/)(backtests?|strateg(y|ies)|portfolio|ppo|alpha[_-]?model|ranker)(/|\\.|$)", re.IGNORECASE),
)


def tracked_text_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for base in CHECK_ROOTS:
        path = root / base
        if not path.exists():
            continue
        files.extend(item for item in path.rglob("*") if item.is_file() and item.suffix in TEXT_SUFFIXES)
    return sorted(files)


def validate(root: Path) -> list[str]:
    failures: list[str] = []
    for path in tracked_text_files(root):
        relative = path.relative_to(root).as_posix()
        for pattern in FORBIDDEN_PATH_PATTERNS:
            if pattern.search(relative):
                failures.append(f"forbidden strategy/index path: {relative}")
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_TEXT:
            if token in text:
                failures.append(f"forbidden project/index coupling token {token!r} in {relative}")
    return failures


def main() -> None:
    failures = validate(Path("."))
    print(json.dumps({"status": "PASS" if not failures else "FAIL", "failures": failures}, sort_keys=True))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
