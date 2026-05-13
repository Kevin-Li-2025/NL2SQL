from __future__ import annotations

from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


def torch_dtype(name: str | None) -> torch.dtype | str:
    if not name or name == "auto":
        return "auto"
    mapping = {
        "bfloat16": torch.bfloat16,
        "bf16": torch.bfloat16,
        "float16": torch.float16,
        "fp16": torch.float16,
        "float32": torch.float32,
        "fp32": torch.float32,
    }
    if name not in mapping:
        raise ValueError(f"Unsupported torch dtype: {name}")
    return mapping[name]


def load_tokenizer(model_name: str, trust_remote_code: bool = True) -> Any:
    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=trust_remote_code)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"
    return tokenizer


def quantization_config(load_in_4bit: bool) -> Any | None:
    if not load_in_4bit:
        return None
    from transformers import BitsAndBytesConfig

    return BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
    )


def load_causal_lm(model_config: dict[str, Any]) -> Any:
    kwargs: dict[str, Any] = {
        "device_map": model_config.get("device_map", "auto"),
        "torch_dtype": torch_dtype(model_config.get("torch_dtype")),
        "quantization_config": quantization_config(bool(model_config.get("load_in_4bit", False))),
        "trust_remote_code": bool(model_config.get("trust_remote_code", True)),
    }
    if model_config.get("attn_implementation"):
        kwargs["attn_implementation"] = model_config["attn_implementation"]

    return AutoModelForCausalLM.from_pretrained(
        model_config["base_model"],
        **kwargs,
    )


def apply_liger_kernel_if_requested(model: Any, model_config: dict[str, Any]) -> Any:
    if not model_config.get("use_liger_kernel", False):
        return model

    model_type = getattr(model.config, "model_type", "")
    try:
        from liger_kernel.transformers import apply_liger_kernel_to_qwen2
    except ImportError as exc:
        raise ImportError(
            "use_liger_kernel=true requires `pip install liger-kernel`. "
            "Install the optional perf dependencies before running the MFU config."
        ) from exc

    if model_type not in {"qwen2"}:
        raise ValueError(f"Liger Qwen2 patch does not support model_type={model_type!r}")

    liger = model_config.get("liger", {})
    apply_liger_kernel_to_qwen2(
        rope=bool(liger.get("rope", True)),
        rms_norm=bool(liger.get("rms_norm", True)),
        swiglu=bool(liger.get("swiglu", True)),
        cross_entropy=bool(liger.get("cross_entropy", False)),
        fused_linear_cross_entropy=bool(liger.get("fused_linear_cross_entropy", True)),
        model=model,
    )
    return model
