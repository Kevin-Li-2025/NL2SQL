from nl2sql_l20.packing import IGNORE_INDEX, pack_tokenized_records


def test_pack_tokenized_records_pads_to_fixed_length() -> None:
    records = [
        {"input_ids": [1, 2], "labels": [IGNORE_INDEX, 2]},
        {"input_ids": [3], "labels": [3]},
    ]
    packed = pack_tokenized_records(records, max_seq_length=4, pad_token_id=0)
    assert len(packed) == 1
    assert packed[0]["input_ids"] == [1, 2, 3, 0]
    assert packed[0]["labels"] == [IGNORE_INDEX, 2, 3, IGNORE_INDEX]


def test_pack_tokenized_records_starts_new_block_when_full() -> None:
    records = [
        {"input_ids": [1, 2, 3], "labels": [1, 2, 3]},
        {"input_ids": [4, 5], "labels": [4, 5]},
    ]
    packed = pack_tokenized_records(records, max_seq_length=4, pad_token_id=0)
    assert len(packed) == 2
    assert packed[0]["input_ids"] == [1, 2, 3, 0]
    assert packed[1]["input_ids"] == [4, 5, 0, 0]
