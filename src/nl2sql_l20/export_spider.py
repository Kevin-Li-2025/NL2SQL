from __future__ import annotations

import argparse
from pathlib import Path

from nl2sql_l20.io import read_jsonl


def export_spider_files(
    gold_jsonl: str | Path,
    pred_jsonl: str | Path,
    out_dir: str | Path,
) -> tuple[Path, Path]:
    gold_rows = list(read_jsonl(gold_jsonl))
    pred_by_id = {row["id"]: row for row in read_jsonl(pred_jsonl)}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    gold_path = out_dir / "gold.txt"
    pred_path = out_dir / "pred.txt"
    with gold_path.open("w", encoding="utf-8") as gold_handle, pred_path.open(
        "w", encoding="utf-8"
    ) as pred_handle:
        for row in gold_rows:
            pred = pred_by_id.get(row["id"], {})
            gold_handle.write(f"{row['sql']}\t{row['db_id']}\n")
            pred_handle.write(f"{pred.get('prediction', '')}\n")

    return gold_path, pred_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export predictions to Spider official evaluator text files."
    )
    parser.add_argument("--gold-jsonl", required=True)
    parser.add_argument("--pred-jsonl", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    gold_path, pred_path = export_spider_files(args.gold_jsonl, args.pred_jsonl, args.out_dir)
    print(f"Wrote {gold_path} and {pred_path}")


if __name__ == "__main__":
    main()
