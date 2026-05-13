from nl2sql_l20.cost_curve import balanced_candidate_subset, select_prediction_for_budget


def test_balanced_candidate_subset_round_robins_architectures() -> None:
    candidates = [
        {"architecture": "rich_context", "sample_index": 0},
        {"architecture": "rich_context", "sample_index": 1},
        {"architecture": "query_plan", "sample_index": 0},
        {"architecture": "query_plan", "sample_index": 1},
        {"architecture": "skeleton", "sample_index": 0},
        {"architecture": "skeleton", "sample_index": 1},
    ]

    selected = balanced_candidate_subset(candidates, budget=4)

    assert [(row["architecture"], row["sample_index"]) for row in selected] == [
        ("rich_context", 0),
        ("query_plan", 0),
        ("skeleton", 0),
        ("rich_context", 1),
    ]


def test_select_prediction_for_budget_uses_only_budgeted_candidates() -> None:
    row = {
        "id": "ex-1",
        "benchmark": "unit",
        "db_id": "db",
        "question": "Which rows?",
        "schema_text": "CREATE TABLE item (\n  id INTEGER\n);",
        "value_hints": {},
    }
    prediction_row = {
        "id": "ex-1",
        "candidates": [
            {
                "architecture": "rich_context",
                "sample_index": 0,
                "prediction": "select id from item",
                "normalized_prediction": "select id from item",
                "executable": True,
                "result_signature": "a",
                "result_degenerate": False,
                "result_row_count": 1,
            },
            {
                "architecture": "query_plan",
                "sample_index": 0,
                "prediction": "select id from item",
                "normalized_prediction": "select id from item",
                "executable": True,
                "result_signature": "a",
                "result_degenerate": False,
                "result_row_count": 1,
            },
            {
                "architecture": "skeleton",
                "sample_index": 0,
                "prediction": "select missing from item",
                "normalized_prediction": "select missing from item",
                "executable": False,
                "result_signature": "",
                "result_degenerate": None,
                "result_row_count": None,
            },
        ],
    }

    selected = select_prediction_for_budget(
        row=row,
        prediction_row=prediction_row,
        budget=2,
        strategy="value_aware_voting",
        subset_policy="balanced",
    )

    assert selected["prediction"] == "select id from item"
    assert selected["candidate_budget"] == 2
