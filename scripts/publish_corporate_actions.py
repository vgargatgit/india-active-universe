from __future__ import annotations

import argparse
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    rows = [json.loads(line) for line in Path(args.input).read_text(encoding="utf-8").splitlines() if line.strip()]
    schema = pa.schema([
        pa.field("event_id", pa.string()), pa.field("security_id", pa.string()), pa.field("issuer_id", pa.string()), pa.field("exchange", pa.string()), pa.field("symbol_at_event", pa.string()), pa.field("isin", pa.string()), pa.field("series", pa.string()), pa.field("event_type", pa.string()), pa.field("event_date", pa.string()), pa.field("ex_date", pa.string()), pa.field("record_date", pa.string()), pa.field("subject", pa.string()), pa.field("face_value", pa.string()), pa.field("old_face_value", pa.float64()), pa.field("new_face_value", pa.float64()), pa.field("cash_dividend_per_share", pa.float64()), pa.field("dividend_currency", pa.string()), pa.field("dividend_amount_quality", pa.string()), pa.field("ratio_raw", pa.string()), pa.field("ratio_numerator", pa.int64()), pa.field("ratio_denominator", pa.int64()), pa.field("price_factor", pa.float64()), pa.field("share_factor", pa.float64()), pa.field("source", pa.string()), pa.field("source_file_id", pa.string()), pa.field("source_quality", pa.string()), pa.field("review_status", pa.string()), pa.field("notes", pa.string()), pa.field("review_classification", pa.string()), pa.field("classification_confidence", pa.string()), pa.field("factor_quality", pa.string()), pa.field("resolution_type", pa.string()), pa.field("evidence_references", pa.list_(pa.string())), pa.field("review_rationale", pa.string()), pa.field("bonus_ratio", pa.float64()), pa.field("rights_ratio", pa.float64()), pa.field("rights_subscription_price", pa.float64()), pa.field("post_share_count_per_old_share", pa.float64()), pa.field("cash_contribution_per_old_share", pa.float64()), pa.field("rights_entitlement_basis", pa.string()), pa.field("bonus_ratio_numerator", pa.int64()), pa.field("bonus_ratio_denominator", pa.int64()), pa.field("eligibility_scope", pa.string()), pa.field("pre_event_total_shares", pa.float64()), pa.field("post_event_total_shares", pa.float64()), pa.field("public_holder_share_factor", pa.float64()), pa.field("promoter_holder_share_factor", pa.float64())
    ])
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), target, compression="zstd", use_dictionary=True)
    print(f"corporate_actions={len(rows)}")


if __name__ == "__main__":
    main()
