#!/usr/bin/env python3
"""Optional OCR workflow for scanned official delisting notices.

The command never changes the inventory or canonical identities. It writes OCR
text as separate evidence and requires external `pdftoppm` and `tesseract`
executables. This makes missing OCR tooling an explicit state, not a parse
success.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    missing = [tool for tool in ("pdftoppm", "tesseract") if shutil.which(tool) is None]
    if missing:
        raise SystemExit("OCR_UNAVAILABLE: install external tools: " + ", ".join(missing))

    con = duckdb.connect()
    rows = con.execute(
        "SELECT source_file_id FROM read_parquet(?) WHERE parse_status = 'SCANNED_DOCUMENT_OCR_REQUIRED'",
        [args.inventory],
    ).fetchall()
    output = []
    for (source_file_id,) in rows:
        pdf = Path(args.input_dir) / source_file_id
        if not pdf.exists():
            output.append({"source_file_id": source_file_id, "ocr_status": "SOURCE_MISSING", "ocr_text": None, "source_sha256": None})
            continue
        digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory(prefix="india-equity-ocr-") as tmp:
            prefix = Path(tmp) / "page"
            subprocess.run(["pdftoppm", "-png", "-r", "250", str(pdf), str(prefix)], check=True)
            text_parts = []
            for image in sorted(Path(tmp).glob("page-*.png")):
                result = subprocess.run(["tesseract", str(image), "stdout", "-l", "eng"], check=True, capture_output=True, text=True)
                text_parts.append(result.stdout)
        output.append({"source_file_id": source_file_id, "ocr_status": "OCR_TEXT_EXTRACTED", "ocr_text": "\n".join(text_parts), "source_sha256": digest})
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(output), args.output, compression="zstd")
    print(f"ocr_rows={len(output)}")


if __name__ == "__main__":
    main()
