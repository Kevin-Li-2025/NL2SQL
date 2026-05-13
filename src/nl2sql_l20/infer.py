from __future__ import annotations

import argparse
from pathlib import Path

from tqdm.auto import tqdm

from nl2sql_l20.config import load_config, require
from nl2sql_l20.io import read_jsonl, write_jsonl
from nl2sql_l20.prompts import ARCHITECTURES, apply_chat_template, build_messages
from nl2sql_l20.sql import extract_sql


def main() -> None:
    parser = argparse.ArgumentParser(description="Run NL2SQL inference.")
    parser.add_argument("--config", required=True, help="Experiment YAML config.")
    parser.add_argument("--input", required=True, help="Prepared JSONL file.")
    parser.add_argument("--output", required=True, help="Prediction JSONL path.")
    parser.add_argument("--adapter", default=None, help="Optional LoRA adapter path.")
    parser.add_argument("--architecture", default=None, choices=ARCHITECTURES)
    parser.add_argument("--max-examples", type=int, default=None)
    args = parser.parse_args()

    config = load_config(args.config)
    architecture = args.architecture or require(config, "experiment.architecture")
    model_config = require(config, "model")
    generation = config.get("generation", {})

    import torch
    from peft import PeftModel

    from nl2sql_l20.modeling import load_causal_lm, load_tokenizer

    tokenizer = load_tokenizer(
        model_config["base_model"],
        trust_remote_code=bool(model_config.get("trust_remote_code", True)),
    )
    model = load_causal_lm(model_config)
    if args.adapter:
        model = PeftModel.from_pretrained(model, args.adapter)
    model.eval()

    rows = list(read_jsonl(args.input))
    if args.max_examples is not None:
        rows = rows[: args.max_examples]

    predictions = []
    for row in tqdm(rows, desc="Generating SQL"):
        prompt = apply_chat_template(
            tokenizer,
            build_messages(row, architecture),
            add_generation_prompt=True,
        )
        encoded = tokenizer(prompt, return_tensors="pt").to(model.device)
        temperature = float(generation.get("temperature", 0.0))
        generate_kwargs = {
            "max_new_tokens": int(generation.get("max_new_tokens", 512)),
            "do_sample": temperature > 0,
            "top_p": float(generation.get("top_p", 1.0)),
            "pad_token_id": tokenizer.pad_token_id,
            "eos_token_id": tokenizer.eos_token_id,
        }
        if temperature > 0:
            generate_kwargs["temperature"] = temperature
        with torch.no_grad():
            output_ids = model.generate(
                **encoded,
                **generate_kwargs,
            )
        generated = output_ids[0, encoded["input_ids"].shape[1] :]
        text = tokenizer.decode(generated, skip_special_tokens=True)
        sql = extract_sql(text)
        predictions.append(
            {
                "id": row["id"],
                "benchmark": row.get("benchmark", ""),
                "db_id": row["db_id"],
                "question": row["question"],
                "prediction": sql,
                "raw_generation": text.strip(),
            }
        )

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    count = write_jsonl(args.output, predictions)
    print(f"Wrote {count} predictions to {args.output}")


if __name__ == "__main__":
    main()
