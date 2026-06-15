from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from src.utils.io import ensure_dir, save_json, save_jsonl
from src.utils.text import normalize_text


DEFAULT_INSTRUCTION = (
    "Ban la tro ly phap ly tieng Viet. "
    "Chi duoc tra loi dua tren van ban phap ly duoc cung cap. "
    "Tra loi ngan, truc tiep, co can cu phap ly, lap luan ngan va thong tin con thieu neu evidence chua du. "
    "Khong duoc dua them thong tin ngoai evidence."
)


@dataclass(frozen=True)
class SFTBuildConfig:
    output_dir: str = "data/processed/thangvip_legalqa"
    train_ratio: float = 0.9
    val_ratio: float = 0.05
    random_seed: int = 42
    reasoning_ratio: float = 1.0
    max_samples: int = 0
    instruction: str = DEFAULT_INSTRUCTION


def build_runpod_sft_dataset(records: list[dict], config: SFTBuildConfig | None = None) -> dict[str, Path]:
    active_config = config or SFTBuildConfig()
    materialized = _materialize_examples(records, active_config)
    train_records, val_records, test_records = _split_records(materialized, active_config)

    output_dir = ensure_dir(active_config.output_dir)
    paths = {
        "train": output_dir / "train.jsonl",
        "val": output_dir / "val.jsonl",
        "test": output_dir / "test.jsonl",
        "manifest": output_dir / "manifest.json",
    }
    save_jsonl(paths["train"], train_records)
    save_jsonl(paths["val"], val_records)
    save_jsonl(paths["test"], test_records)
    save_json(
        paths["manifest"],
        {
            "instruction": active_config.instruction,
            "total_records": len(materialized),
            "train_records": len(train_records),
            "val_records": len(val_records),
            "test_records": len(test_records),
            "reasoning_ratio": active_config.reasoning_ratio,
            "output_format": "jsonl",
            "fields": ["messages", "metadata"],
        },
    )
    return paths


def build_reasoning_target(record: dict) -> str:
    doc_name = str(record.get("doc_name", "")).strip() or "Van ban phap ly"
    article_content = str(record.get("article_content", "")).strip()
    question = str(record.get("question", "")).strip()
    answer = str(record.get("answer", "")).strip()
    if not answer:
        return ""

    article_number = _infer_article_number(article_content)
    legal_basis = doc_name
    if article_number:
        legal_basis = f"{doc_name} - Dieu {article_number}"

    conclusion = answer.rstrip(".")
    reasoning = _build_short_reasoning(question, answer)
    return "\n".join(
        [
            f"Tra loi: {conclusion}.",
            f"Can cu: {legal_basis}.",
            f"Lap luan: {reasoning}",
            "Thong tin con thieu: Khong co them thong tin can bo sung neu chi dua tren evidence hien co.",
        ]
    ).strip()


def _build_short_reasoning(question: str, answer: str) -> str:
    if not question:
        return f"Evidence duoc cung cap neu truc tiep noi dung '{answer}', vi vay ket luan nhu tren."
    return "Evidence duoc cung cap khop voi noi dung cau hoi; do do cau tra loi chi rut ra tu dieu/khoan nay va khong suy doan ngoai van ban."


def build_chat_example(record: dict, instruction: str, use_reasoning_format: bool) -> dict:
    article_content = str(record.get("article_content", "")).strip()
    question = str(record.get("question", "")).strip()
    answer = str(record.get("answer", "")).strip()
    if use_reasoning_format:
        answer = build_reasoning_target(record)

    return {
        "messages": [
            {"role": "system", "content": instruction.strip()},
            {
                "role": "user",
                "content": (
                    "Van ban phap ly:\n"
                    f"{article_content}\n\n"
                    "Cau hoi:\n"
                    f"{question}\n\n"
                    "Yeu cau:\n"
                    "Tra loi ngan, truc tiep.\n"
                    "Neu can cu phap ly va lap luan ngan dua tren evidence.\n"
                    "Phai co citation neu co the.\n"
                    "Khong duoc dua them van ban ngoai evidence.\n"
                ).strip(),
            },
            {"role": "assistant", "content": answer},
        ],
        "metadata": {
            "record_id": record.get("record_id"),
            "doc_name": record.get("doc_name", ""),
            "doc_type_name": record.get("doc_type_name", ""),
            "question_type": record.get("question_type", ""),
            "difficulty": record.get("difficulty", ""),
            "format": "reasoning" if use_reasoning_format else "plain",
        },
    }


def _materialize_examples(records: list[dict], config: SFTBuildConfig) -> list[dict]:
    filtered = [record for record in records if str(record.get("question", "")).strip() and str(record.get("answer", "")).strip()]
    if config.max_samples and config.max_samples > 0:
        filtered = filtered[: config.max_samples]

    materialized: list[dict] = []
    for record in filtered:
        use_reasoning_format = True if config.reasoning_ratio >= 1.0 else False
        materialized.append(build_chat_example(record, config.instruction, use_reasoning_format))
    return materialized


def _split_records(records: list[dict], config: SFTBuildConfig) -> tuple[list[dict], list[dict], list[dict]]:
    if not records:
        return [], [], []
    total = len(records)
    train_end = int(total * config.train_ratio)
    val_end = train_end + int(total * config.val_ratio)

    train_records = records[:train_end] or records[: max(total - 2, 1)]
    val_records = records[train_end:val_end]
    test_records = records[val_end:]

    if not val_records and len(records) >= 3:
        val_records = [train_records.pop()]
    if not test_records and len(records) >= 2:
        source = val_records if val_records else train_records
        test_records = [source.pop()]
    return train_records, val_records, test_records


def _infer_article_number(article_content: str) -> str | None:
    normalized = normalize_text(article_content)
    normalized_ascii = normalized.lower()
    match = re.search(r"(?:^|\n)\s*(?:dieu|đieu|điều)\s+(\d+[A-Za-z]?)", normalized_ascii, re.IGNORECASE)
    if match:
        return match.group(1)
    return None
