from __future__ import annotations

import argparse
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from nl2sql_l20.io import read_json, write_jsonl
from nl2sql_l20.schema import (
    DatabaseSchema,
    find_sqlite_database,
    load_spider_schemas,
    load_sqlite_schema,
    serialize_m_schema,
    serialize_schema,
)
from nl2sql_l20.schema_linking import link_schema
from nl2sql_l20.value_hints import collect_value_hints


def _limit(rows: Iterator[dict[str, Any]], max_examples: int | None) -> Iterator[dict[str, Any]]:
    for index, row in enumerate(rows):
        if max_examples is not None and index >= max_examples:
            break
        yield row


def _spider_split_file(spider_dir: Path, split: str) -> Path:
    candidates = {
        "train": ["train_spider.json"],
        "train_others": ["train_others.json"],
        "dev": ["dev.json"],
        "test": ["test.json"],
    }
    for filename in candidates.get(split, [f"{split}.json"]):
        path = spider_dir / filename
        if path.exists():
            return path
    raise FileNotFoundError(f"Could not find Spider split '{split}' under {spider_dir}")


def prepare_spider_rows(
    spider_dir: str | Path,
    split: str,
    max_examples: int | None = None,
    max_value_hints: int = 32,
) -> Iterator[dict[str, Any]]:
    spider_dir = Path(spider_dir)
    schemas = load_spider_schemas(spider_dir / "tables.json")
    rows = read_json(_spider_split_file(spider_dir, split))
    database_root = spider_dir / "database"

    for index, row in enumerate(_limit(iter(rows), max_examples)):
        db_id = row["db_id"]
        schema = schemas[db_id]
        question = row["question"]
        sql = row.get("query") or row.get("sql")
        evidence = row.get("evidence") or ""
        db_path = find_sqlite_database(database_root, db_id)
        links = link_schema(question, schema, evidence)
        yield make_record(
            benchmark="spider",
            split=split,
            index=index,
            db_id=db_id,
            question=question,
            sql=sql,
            schema=schema,
            evidence=evidence,
            db_path=db_path,
            links=links,
            max_value_hints=max_value_hints,
        )


def _bird_split_file(bird_dir: Path, split: str) -> Path:
    candidates = [
        bird_dir / split / f"{split}.json",
        bird_dir / f"{split}.json",
        bird_dir / f"{split}_sqlite.json",
        bird_dir / f"{split}_data_sqlite.json",
        bird_dir / f"{split}_data.json",
        bird_dir / f"{split}_filtered.json",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(f"Could not find BIRD split '{split}' under {bird_dir}")


def _bird_db_root(bird_dir: Path, split: str) -> Path:
    candidates = [
        bird_dir / split / f"{split}_databases",
        bird_dir / f"{split}_databases",
        bird_dir / "dev_databases",
        bird_dir / "databases",
        bird_dir / "database",
        bird_dir,
    ]
    for path in candidates:
        if path.exists():
            return path
    return bird_dir


def prepare_bird_rows(
    bird_dir: str | Path,
    split: str,
    max_examples: int | None = None,
    max_value_hints: int = 32,
) -> Iterator[dict[str, Any]]:
    bird_dir = Path(bird_dir)
    rows = read_json(_bird_split_file(bird_dir, split))
    database_root = _bird_db_root(bird_dir, split)
    schema_cache: dict[str, DatabaseSchema] = {}

    for index, row in enumerate(_limit(iter(rows), max_examples)):
        db_id = row["db_id"]
        db_path = find_sqlite_database(database_root, db_id)
        if db_path is None:
            raise FileNotFoundError(f"Could not find SQLite database for db_id={db_id}")
        if db_id not in schema_cache:
            schema_cache[db_id] = load_sqlite_schema(db_path, db_id=db_id)

        question = row["question"]
        sql = row.get("SQL") or row.get("query") or row.get("sql")
        evidence = row.get("evidence") or ""
        schema = schema_cache[db_id]
        links = link_schema(question, schema, evidence)
        yield make_record(
            benchmark="bird",
            split=split,
            index=index,
            db_id=db_id,
            question=question,
            sql=sql,
            schema=schema,
            evidence=evidence,
            db_path=db_path,
            links=links,
            max_value_hints=max_value_hints,
        )


def make_record(
    benchmark: str,
    split: str,
    index: int,
    db_id: str,
    question: str,
    sql: str,
    schema: DatabaseSchema,
    evidence: str = "",
    db_path: str | Path | None = None,
    links: dict[str, list[str]] | None = None,
    max_value_hints: int = 32,
) -> dict[str, Any]:
    if not sql:
        raise ValueError(f"Missing SQL for {benchmark}:{split}:{index}")
    links = links or {"tables": [], "columns": []}
    value_hints = (
        collect_value_hints(
            db_path,
            schema,
            question,
            evidence,
            max_hints=max_value_hints,
            candidate_tables=links.get("tables"),
            candidate_columns=links.get("columns"),
        )
        if db_path
        else {}
    )
    return {
        "id": f"{benchmark}-{split}-{index:06d}",
        "benchmark": benchmark,
        "split": split,
        "db_id": db_id,
        "dialect": "sqlite",
        "question": question,
        "evidence": evidence,
        "sql": sql.strip(),
        "schema_text": serialize_schema(schema),
        "linked_schema_text": serialize_schema(schema, linked=links),
        "m_schema_text": serialize_m_schema(schema, linked=links, value_hints=value_hints),
        "schema_links": links,
        "value_hints": value_hints,
        "db_path": str(db_path) if db_path else "",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare NL2SQL benchmark JSONL files.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    spider = subparsers.add_parser("spider", help="Prepare Spider 1.0 data.")
    spider.add_argument("--spider-dir", required=True, help="Path containing tables.json and splits.")
    spider.add_argument("--split", default="train", choices=["train", "train_others", "dev", "test"])
    spider.add_argument("--out", required=True, help="Output JSONL path.")
    spider.add_argument("--max-examples", type=int, default=None)
    spider.add_argument("--max-value-hints", type=int, default=32)

    bird = subparsers.add_parser("bird", help="Prepare BIRD-style data from a local unpacked folder.")
    bird.add_argument("--bird-dir", required=True, help="Path containing BIRD split JSON and databases.")
    bird.add_argument("--split", default="dev")
    bird.add_argument("--out", required=True, help="Output JSONL path.")
    bird.add_argument("--max-examples", type=int, default=None)
    bird.add_argument("--max-value-hints", type=int, default=32)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "spider":
        rows = prepare_spider_rows(
            args.spider_dir,
            args.split,
            args.max_examples,
            args.max_value_hints,
        )
    elif args.command == "bird":
        rows = prepare_bird_rows(
            args.bird_dir,
            args.split,
            args.max_examples,
            args.max_value_hints,
        )
    else:
        raise ValueError(f"Unknown command: {args.command}")

    count = write_jsonl(args.out, rows)
    print(f"Wrote {count} rows to {args.out}")


if __name__ == "__main__":
    main()
