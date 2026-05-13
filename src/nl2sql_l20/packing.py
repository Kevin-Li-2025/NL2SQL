from __future__ import annotations

from collections.abc import Iterable
from typing import Any


IGNORE_INDEX = -100


def pad_record(
    input_ids: list[int],
    labels: list[int],
    max_seq_length: int,
    pad_token_id: int,
) -> dict[str, list[int]]:
    pad_length = max_seq_length - len(input_ids)
    if pad_length < 0:
        raise ValueError("Cannot pad a record longer than max_seq_length")
    return {
        "input_ids": input_ids + [pad_token_id] * pad_length,
        "labels": labels + [IGNORE_INDEX] * pad_length,
    }


def pack_tokenized_records(
    records: Iterable[dict[str, Any]],
    max_seq_length: int,
    pad_token_id: int,
    drop_remainder: bool = False,
) -> list[dict[str, list[int]]]:
    packed: list[dict[str, list[int]]] = []
    current_ids: list[int] = []
    current_labels: list[int] = []

    for record in records:
        input_ids = list(record["input_ids"])
        labels = list(record["labels"])
        if len(input_ids) != len(labels):
            raise ValueError("input_ids and labels must have the same length")
        if len(input_ids) > max_seq_length:
            input_ids = input_ids[:max_seq_length]
            labels = labels[:max_seq_length]

        if current_ids and len(current_ids) + len(input_ids) > max_seq_length:
            packed.append(pad_record(current_ids, current_labels, max_seq_length, pad_token_id))
            current_ids = []
            current_labels = []

        current_ids.extend(input_ids)
        current_labels.extend(labels)

        if len(current_ids) == max_seq_length:
            packed.append(
                {
                    "input_ids": current_ids,
                    "labels": current_labels,
                }
            )
            current_ids = []
            current_labels = []

    if current_ids and not drop_remainder:
        packed.append(pad_record(current_ids, current_labels, max_seq_length, pad_token_id))

    return packed
