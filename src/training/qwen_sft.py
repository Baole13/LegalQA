from __future__ import annotations

import inspect
from dataclasses import dataclass
from pathlib import Path

from src.training.data import load_json_config, load_training_records
from src.utils.io import ensure_dir, save_json


DEFAULT_SYSTEM_PROMPT = (
    "Ban la tro ly phap ly tieng Viet. "
    "Chi duoc tra loi dua tren cac doan luat duoc cung cap. "
    "Neu context khong du can cu thi phai tra loi: Toi khong biet."
)


@dataclass(frozen=True)
class QwenSFTRecord:
    prompt: str
    answer: str


def load_qwen_sft_config(path: str = "configs/training/runpod.qwen2_5_7b_qlora.json") -> dict:
    return load_json_config(path)


def build_qwen_sft_records(records: list[dict], instruction_template: str = "") -> list[QwenSFTRecord]:
    formatted: list[QwenSFTRecord] = []
    for record in records:
        question = str(record.get("question", "")).strip()
        answer = str(record.get("target") or record.get("answer") or "").strip()
        contexts = record.get("contexts") or []
        if not question or not answer or not contexts:
            continue
        prompt = build_sft_prompt(
            question=question,
            contexts=contexts,
            instruction_template=instruction_template,
        )
        formatted.append(QwenSFTRecord(prompt=prompt, answer=answer))
    return formatted


def build_sft_prompt(question: str, contexts: list[dict], instruction_template: str = "") -> str:
    instruction = (instruction_template or DEFAULT_SYSTEM_PROMPT).strip()
    context_block = format_contexts(contexts)
    return "\n\n".join(
        [
            f"He thong:\n{instruction}",
            f"Cau hoi:\n{question.strip()}",
            f"Chung cu phap ly:\n{context_block}",
            "Yeu cau tra loi:\n"
            "Tra loi ngan gon, dung can cu. "
            "Neu khong co du can cu trong chung cu, phai tra loi: Toi khong biet.",
        ]
    ).strip()


def format_contexts(contexts: list[dict]) -> str:
    lines: list[str] = []
    for index, item in enumerate(contexts, start=1):
        title = str(item.get("doc_name") or item.get("title") or "Van ban phap ly").strip()
        doc_number = str(item.get("doc_number") or "").strip()
        article = str(item.get("article") or "").strip()
        clause = str(item.get("clause") or "").strip()
        text = str(item.get("text") or "").strip()
        metadata_bits = [title]
        if doc_number:
            metadata_bits.append(f"So {doc_number}")
        if article:
            metadata_bits.append(f"Dieu {article}")
        if clause:
            metadata_bits.append(f"Khoan {clause}")
        header = " | ".join(metadata_bits)
        lines.append(f"[{index}] {header}\n{text}")
    return "\n\n".join(lines).strip()


def to_chat_example(prompt: str, answer: str) -> list[dict]:
    return [
        {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
        {"role": "assistant", "content": answer.strip()},
    ]


def train_qwen_sft(config_path: str = "configs/training/runpod.qwen2_5_7b_qlora.json") -> Path:
    try:
        import torch
        from datasets import Dataset
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, TrainingArguments
        from trl import SFTTrainer
        from peft import LoraConfig
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "Missing Qwen SFT dependencies. Install requirements-runpod.txt before running this script."
        ) from exc

    config = load_qwen_sft_config(config_path)
    train_dataset_path = str(config.get("train_dataset_path") or config.get("dataset_path") or "data/aligned/raft_sft.jsonl")
    eval_dataset_path = str(config.get("eval_dataset_path") or "").strip()

    model_name = str(config.get("model_name", "Qwen/Qwen2.5-7B-Instruct"))
    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=bool(config.get("trust_remote_code", False)))
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    train_texts = _load_training_texts(
        train_dataset_path,
        max_samples=int(config.get("max_samples", 0)),
        instruction_template=str(config.get("instruction_template", "")),
        tokenizer=tokenizer,
    )
    if not train_texts:
        raise SystemExit("No Qwen SFT records found. Run scripts/prepare_training_data.py first.")
    eval_texts = _load_training_texts(
        eval_dataset_path,
        max_samples=int(config.get("max_eval_samples", 0)),
        instruction_template=str(config.get("instruction_template", "")),
        tokenizer=tokenizer,
    ) if eval_dataset_path else []

    quantization_config = None
    if bool(config.get("use_4bit", True)):
        quantization_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type=str(config.get("bnb_4bit_quant_type", "nf4")),
            bnb_4bit_use_double_quant=bool(config.get("bnb_4bit_use_double_quant", True)),
            bnb_4bit_compute_dtype=getattr(torch, str(config.get("bnb_4bit_compute_dtype", "float16"))),
        )

    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        trust_remote_code=bool(config.get("trust_remote_code", False)),
        device_map=config.get("device_map", "auto"),
        torch_dtype=getattr(torch, str(config.get("torch_dtype", "float16"))),
        quantization_config=quantization_config,
    )
    model.config.use_cache = False

    dataset = Dataset.from_list([{"text": text} for text in train_texts])
    eval_dataset = Dataset.from_list([{"text": text} for text in eval_texts]) if eval_texts else None

    lora_config = LoraConfig(
        r=int(config.get("lora_r", 16)),
        lora_alpha=int(config.get("lora_alpha", 32)),
        lora_dropout=float(config.get("lora_dropout", 0.05)),
        bias=str(config.get("lora_bias", "none")),
        task_type="CAUSAL_LM",
        target_modules=list(config.get("target_modules") or ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]),
    )

    output_dir = ensure_dir(config.get("output_dir", "models/qwen-legalqa-sft"))
    training_args_kwargs = {
        "output_dir": str(output_dir),
        "num_train_epochs": float(config.get("num_train_epochs", 2)),
        "per_device_train_batch_size": int(config.get("per_device_train_batch_size", 1)),
        "gradient_accumulation_steps": int(config.get("gradient_accumulation_steps", 16)),
        "learning_rate": float(config.get("learning_rate", 2e-4)),
        "warmup_ratio": float(config.get("warmup_ratio", 0.05)),
        "logging_steps": int(config.get("logging_steps", 10)),
        "save_steps": int(config.get("save_steps", 100)),
        "save_total_limit": int(config.get("save_total_limit", 2)),
        "optim": str(config.get("optim", "paged_adamw_8bit")),
        "lr_scheduler_type": str(config.get("lr_scheduler_type", "cosine")),
        "weight_decay": float(config.get("weight_decay", 0.01)),
        "bf16": bool(config.get("bf16", False)),
        "fp16": bool(config.get("fp16", True)),
        "gradient_checkpointing": bool(config.get("gradient_checkpointing", True)),
        "report_to": list(config.get("report_to") or []),
        "remove_unused_columns": False,
    }
    training_args_signature = inspect.signature(TrainingArguments.__init__)
    training_args_params = set(training_args_signature.parameters)
    if eval_dataset is not None:
        if "evaluation_strategy" in training_args_params:
            training_args_kwargs["evaluation_strategy"] = "steps"
        elif "eval_strategy" in training_args_params:
            training_args_kwargs["eval_strategy"] = "steps"
        if "eval_steps" in training_args_params:
            training_args_kwargs["eval_steps"] = int(config.get("eval_steps", 100))
    training_args = TrainingArguments(**training_args_kwargs)

    trainer_kwargs = {
        "model": model,
        "args": training_args,
        "train_dataset": dataset,
        "peft_config": lora_config,
    }
    if eval_dataset is not None:
        trainer_kwargs["eval_dataset"] = eval_dataset
    trainer_signature = inspect.signature(SFTTrainer.__init__)
    trainer_params = set(trainer_signature.parameters)

    if "processing_class" in trainer_params:
        trainer_kwargs["processing_class"] = tokenizer
    elif "tokenizer" in trainer_params:
        trainer_kwargs["tokenizer"] = tokenizer

    if "dataset_text_field" in trainer_params:
        trainer_kwargs["dataset_text_field"] = "text"

    if "max_seq_length" in trainer_params:
        trainer_kwargs["max_seq_length"] = int(config.get("max_seq_length", 2048))

    trainer = SFTTrainer(**trainer_kwargs)
    trainer.train(resume_from_checkpoint=config.get("resume_from_checkpoint") or None)
    trainer.save_model(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))
    save_json(
        output_dir / "training_manifest.json",
        {
            "base_model": model_name,
            "train_records": len(train_texts),
            "eval_records": len(eval_texts),
            "dataset_path": train_dataset_path,
            "config_path": config_path,
        },
    )
    return Path(output_dir)


def _load_training_texts(path: str, max_samples: int, instruction_template: str, tokenizer) -> list[str]:
    if not path:
        return []
    raw_records = load_training_records(path, max_samples=max_samples)
    if not raw_records:
        return []
    first_record = raw_records[0]
    if "messages" in first_record:
        return [_render_message_record(record, tokenizer) for record in raw_records if record.get("messages")]
    train_records = build_qwen_sft_records(raw_records, instruction_template=instruction_template)
    return [_render_training_text(tokenizer, record.prompt, record.answer) for record in train_records]


def _render_training_text(tokenizer, prompt: str, answer: str) -> str:
    messages = to_chat_example(prompt=prompt, answer=answer)
    if tokenizer is not None and hasattr(tokenizer, "apply_chat_template"):
        return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
    return "\n\n".join(
        [
            f"System: {messages[0]['content']}",
            f"User: {messages[1]['content']}",
            f"Assistant: {messages[2]['content']}",
        ]
    )


def _render_message_record(record: dict, tokenizer) -> str:
    messages = record.get("messages") or []
    if tokenizer is not None and hasattr(tokenizer, "apply_chat_template"):
        return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
    lines: list[str] = []
    for message in messages:
        role = str(message.get("role", "user")).capitalize()
        content = str(message.get("content", "")).strip()
        if not content:
            continue
        lines.append(f"{role}: {content}")
    return "\n\n".join(lines).strip()
