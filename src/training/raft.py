from __future__ import annotations

from dataclasses import dataclass

from src.data.load_qa import load_qa_records, parse_context_list
from src.utils.io import ensure_dir, save_jsonl


@dataclass(frozen=True)
class RaftBuildConfig:
    positive_ratio: float = 0.8
    contexts_per_sample: int = 4
    distractors_per_positive: int = 2
    output_path: str = "data/aligned/raft_sft.jsonl"


def build_raft_training_records(
    aligned_pairs: list[dict],
    retrieval_lookup: dict[str, list[dict]],
    qa_path: str = "data/train.parquet",
    config: RaftBuildConfig | None = None,
) -> list[dict]:
    active_config = config or RaftBuildConfig()
    qa_records = load_qa_records(qa_path)
    qa_by_question = {str(record.get("question", "")).strip(): record for record in qa_records}
    positives: list[dict] = []
    negatives: list[dict] = []

    for pair in aligned_pairs:
        question = str(pair.get("query", "")).strip()
        if not question:
            continue
        qa_record = qa_by_question.get(question, {})
        answer = _resolve_answer_text(qa_record, pair)
        if not answer:
            continue

        candidates = retrieval_lookup.get(question, [])
        positive_chunk_id = str(pair.get("positive_chunk_id", ""))
        positive_context = _to_context_record(
            {
                "chunk_id": positive_chunk_id,
                "cid": pair.get("positive_cid"),
                "text": pair.get("positive_text", ""),
            },
            is_gold=True,
        )
        distractor_candidates = [
            item
            for item in candidates
            if str(item.get("chunk_id", "")) != positive_chunk_id and str(item.get("cid", "")) != str(pair.get("positive_cid", ""))
        ]
        distractors = [
            _to_context_record(item, is_gold=False)
            for item in distractor_candidates[: active_config.distractors_per_positive]
        ]

        positive_contexts = [positive_context, *distractors][: active_config.contexts_per_sample]
        positives.append(
            {
                "question": question,
                "contexts": positive_contexts,
                "answer": answer,
                "target": answer,
                "contains_answer": True,
                "task_type": "raft_positive",
                "gold_chunk_ids": [positive_chunk_id],
                "metadata": {
                    "qa_id": pair.get("qa_id"),
                    "gold_cids": pair.get("gold_cids", []),
                },
            }
        )

        negative_contexts = [
            _to_context_record(item, is_gold=False)
            for item in distractor_candidates[: active_config.contexts_per_sample]
        ]
        if negative_contexts:
            negatives.append(
                {
                    "question": question,
                    "contexts": negative_contexts,
                    "answer": "Toi khong biet.",
                    "target": "Toi khong biet.",
                    "contains_answer": False,
                    "task_type": "raft_distractor",
                    "gold_chunk_ids": [],
                    "metadata": {
                        "qa_id": pair.get("qa_id"),
                        "gold_cids": pair.get("gold_cids", []),
                    },
                }
            )

    final_records = _mix_by_ratio(positives, negatives, positive_ratio=active_config.positive_ratio)
    ensure_dir("data/aligned")
    save_jsonl(active_config.output_path, final_records)
    return final_records


def _resolve_answer_text(qa_record: dict, pair: dict) -> str:
    direct_answer = str(qa_record.get("answer", "") or qa_record.get("final_answer", "") or "").strip()
    if direct_answer:
        return direct_answer
    context_list = parse_context_list(qa_record.get("context_list"))
    if context_list:
        return context_list[0]
    return str(pair.get("positive_text", "")).strip()


def _to_context_record(item: dict, is_gold: bool) -> dict:
    return {
        "chunk_id": item.get("chunk_id"),
        "cid": item.get("cid"),
        "doc_name": item.get("doc_name") or item.get("title"),
        "doc_number": item.get("doc_number"),
        "chapter": item.get("chapter"),
        "article": item.get("article"),
        "clause": item.get("clause"),
        "effective_date": item.get("effective_date"),
        "validity_status": item.get("validity_status"),
        "text": item.get("text", ""),
        "is_gold": is_gold,
    }


def _mix_by_ratio(positives: list[dict], negatives: list[dict], positive_ratio: float) -> list[dict]:
    if not positives:
        return []
    max_negative_count = int(len(positives) * ((1 - positive_ratio) / max(positive_ratio, 1e-6)))
    selected_negatives = negatives[:max_negative_count] if max_negative_count > 0 else []
    return [*positives, *selected_negatives]
