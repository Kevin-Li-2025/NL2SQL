from nl2sql_l20.pipeline import (
    result_is_degenerate,
    select_candidate_execution_guided,
    select_candidate_value_aware,
)


def test_result_is_degenerate_rejects_empty_and_zero_like_results() -> None:
    assert result_is_degenerate([]) is True
    assert result_is_degenerate([(0,)]) is True
    assert result_is_degenerate([(None, "0.0")]) is True
    assert result_is_degenerate([(3,)]) is False


def test_value_aware_selection_prefers_largest_non_degenerate_result_group() -> None:
    candidates = [
        {
            "prediction": "select 0",
            "architecture": "rich_context",
            "sample_index": 0,
            "executable": True,
            "result_signature": "zero",
            "result_degenerate": True,
            "result_row_count": 1,
            "normalized_prediction": "select 0",
        },
        {
            "prediction": "select name from singer",
            "architecture": "query_plan",
            "sample_index": 0,
            "executable": True,
            "result_signature": "names",
            "result_degenerate": False,
            "result_row_count": 3,
            "normalized_prediction": "select name from singer",
        },
        {
            "prediction": "select Name from singer",
            "architecture": "skeleton",
            "sample_index": 1,
            "executable": True,
            "result_signature": "names",
            "result_degenerate": False,
            "result_row_count": 3,
            "normalized_prediction": "select name from singer",
        },
    ]

    selected = select_candidate_value_aware(candidates)

    assert selected["result_signature"] == "names"


def test_execution_guided_selection_prefers_schema_clean_executable_sql() -> None:
    row = {
        "question": "How many singers are there?",
        "schema_text": "\n".join(
            [
                "CREATE TABLE singer (",
                "  singer_id INTEGER,",
                "  name TEXT",
                ");",
            ]
        ),
        "value_hints": {},
    }
    candidates = [
        {
            "prediction": "select count(*) from singer",
            "architecture": "execution_first",
            "sample_index": 0,
            "executable": True,
            "result_signature": "count",
            "result_degenerate": False,
            "result_row_count": 1,
            "normalized_prediction": "select count(*) from singer",
        },
        {
            "prediction": "select count(*) from singers",
            "architecture": "rich_context",
            "sample_index": 0,
            "executable": True,
            "result_signature": "popular_wrong_table",
            "result_degenerate": False,
            "result_row_count": 1,
            "normalized_prediction": "select count(*) from singers",
        },
    ]

    selected = select_candidate_execution_guided(candidates, row)

    assert selected["prediction"] == "select count(*) from singer"
