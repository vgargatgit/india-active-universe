from __future__ import annotations

import argparse
import re
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from collect_nse_suspension_evidence import TextParser, article_date, candidate_names, effective_date, event_type


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--raw-dir", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    output = []
    for row in pq.read_table(args.evidence).to_pylist():
        path = Path(args.raw_dir) / row["source_file_id"]
        parser_text = TextParser()
        parser_text.feed(path.read_text(encoding="utf-8", errors="replace"))
        text = "\n".join(parser_text.parts)
        output.append({**row, "published_date": article_date(text) or row.get("published_date"), "event_type": event_type(text), "effective_date": effective_date(text), "historical_company_names": candidate_names(text), "text_excerpt": re.sub(r"\s+", " ", text).strip()[:1200]})
    fields = list(pq.read_schema(args.evidence))
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(output, schema=pq.read_schema(args.evidence)), target, compression="zstd", use_dictionary=True)
    print({"rows": len(output), "raw_files_rebuilt": len({row["source_file_id"] for row in output})})


if __name__ == "__main__":
    main()
