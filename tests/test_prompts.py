from nl2sql_l20.prompts import build_messages


ROW = {
    "db_id": "concert_singer",
    "dialect": "sqlite",
    "question": "List singer names.",
    "evidence": "",
    "schema_text": "CREATE TABLE singer (name text);",
    "linked_schema_text": "-- tables: singer\nCREATE TABLE singer (name text);",
}


def test_direct_prompt_contains_schema_and_question() -> None:
    messages = build_messages(ROW, "direct")
    assert "CREATE TABLE singer" in messages[1]["content"]
    assert "List singer names." in messages[1]["content"]


def test_schema_aware_prompt_contains_hints() -> None:
    messages = build_messages(ROW, "schema_aware")
    assert "Schema with relevance hints" in messages[1]["content"]
    assert "-- tables: singer" in messages[1]["content"]


def test_bird_specific_prompts_include_rich_context() -> None:
    for architecture in ("evidence_first", "value_grounded", "join_path"):
        messages = build_messages(ROW, architecture)
        assert "M-Schema:" in messages[1]["content"]
        assert "Matched database values:" in messages[1]["content"]
        assert "List singer names." in messages[1]["content"]
