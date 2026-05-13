from nl2sql_l20.candidate_data import build_repair_row, format_candidate_context
from nl2sql_l20.prompts import build_messages


ROW = {
    "id": "spider/train/0",
    "benchmark": "spider",
    "db_id": "concert_singer",
    "question": "How many singers are there?",
    "sql": "SELECT count(*) FROM singer;",
    "dialect": "sqlite",
    "schema_text": "CREATE TABLE singer (\n  singer_id INTEGER,\n  name TEXT\n);",
    "m_schema_text": "Table singer: singer_id, name",
    "value_hints": {"singer.name": ["Alice"]},
}


def test_candidate_repair_prompt_contains_ranked_candidate_feedback() -> None:
    repair_row = dict(ROW)
    repair_row["candidate_context"] = "[0] exec=yes rows=1\n    sql: SELECT count(*) FROM singer;"
    repair_row["value_hint_text"] = "- singer.name: Alice"

    messages = build_messages(repair_row, "candidate_repair")

    assert "repair model" in messages[0]["content"]
    assert "Candidate SQL queries and execution feedback" in messages[1]["content"]
    assert "SELECT count(*) FROM singer" in messages[1]["content"]


def test_build_repair_row_sorts_executable_schema_clean_candidate_first() -> None:
    prediction = {
        "id": ROW["id"],
        "candidates": [
            {
                "architecture": "query_plan",
                "sample_index": 0,
                "prediction": "SELECT count(*) FROM missing_table;",
                "normalized_prediction": "select count(*) from missing_table",
                "executable": False,
                "execution_error": "no such table: missing_table",
            },
            {
                "architecture": "rich_context",
                "sample_index": 1,
                "prediction": "SELECT count(*) FROM singer;",
                "normalized_prediction": "select count(*) from singer",
                "executable": True,
                "result_signature": "abc",
                "result_row_count": 1,
                "result_degenerate": False,
            },
        ],
    }

    repair_row = build_repair_row(ROW, prediction, label_candidates=False)

    assert repair_row is not None
    assert "source_index=1" in repair_row["candidate_context"].splitlines()[0]
    assert "schema_violations=0" in repair_row["candidate_context"].splitlines()[0]
    assert repair_row["candidate_count"] == 2


def test_format_candidate_context_truncates_long_sql() -> None:
    context = format_candidate_context(
        [
            {
                "candidate_index": 0,
                "architecture": "rich_context",
                "sample_index": 0,
                "prediction": "SELECT " + "x" * 1000,
                "executable": True,
                "result_row_count": 1,
                "result_degenerate": False,
            }
        ],
        max_sql_chars=40,
    )

    assert "..." in context
    assert len(context.split("sql: ", 1)[1]) <= 40
