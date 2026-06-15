from __future__ import annotations

from dataclasses import dataclass

from src.data.load_qa import load_qa_records, parse_context_list
from src.utils.text import direct_answer_score, keyword_coverage_score, split_sentences, unique_preserve_order
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


def build_raft_records_from_retrieval_records(
    records: list[dict],
    config: RaftBuildConfig | None = None,
) -> list[dict]:
    """Build scalable RAFT samples directly from YuITC-style retrieval records.

    This path is meant for research experiments where YuITC supplies question,
    gold cid(s), and positive context. It filters out records without gold cid,
    mixes gold evidence with near/random distractors, and adds negative refusal
    samples so the model learns grounding instead of memorizing answers.
    """
    active_config = config or RaftBuildConfig()
    usable = [record for record in records if record.get("question") and record.get("positive_context") and record.get("positive_cids")]
    positives: list[dict] = []
    negatives: list[dict] = []

    for index, record in enumerate(usable):
        question = str(record.get("question", "")).strip()
        positive_context = str(record.get("positive_context", "")).strip()
        positive_cids = [str(cid) for cid in record.get("positive_cids", []) if str(cid).strip()]
        if not question or not positive_context or not positive_cids:
            continue

        positive_chunk_id = str(record.get("positive_chunk_id") or f"yuitc:{record.get('query_id', index)}:gold")
        distractors = _select_raft_distractors(record, usable, active_config.contexts_per_sample - 1, anchor_index=index)
        contexts = [
            _to_context_record(
                {
                    "chunk_id": positive_chunk_id,
                    "cid": positive_cids[0],
                    "text": positive_context,
                    "doc_name": record.get("doc_name", ""),
                },
                is_gold=True,
            ),
            *distractors,
        ][: active_config.contexts_per_sample]
        target = _build_concise_raft_target(question, positive_context, contexts[0])
        positives.append(
            {
                "question": question,
                "contexts": contexts,
                "answer": target,
                "target": target,
                "contains_answer": True,
                "task_type": "raft_positive",
                "gold_chunk_ids": [positive_chunk_id],
                "metadata": {
                    "qa_id": record.get("query_id"),
                    "gold_cids": positive_cids,
                    "source": "yuitc",
                },
            }
        )

        negative_contexts = _select_raft_distractors(record, usable, active_config.contexts_per_sample, anchor_index=index)
        if negative_contexts:
            negatives.append(
                {
                    "question": question,
                    "contexts": negative_contexts,
                    "answer": "Toi khong biet. Khong co can cu phap ly du sat trong evidence duoc cung cap.",
                    "target": "Toi khong biet. Khong co can cu phap ly du sat trong evidence duoc cung cap.",
                    "contains_answer": False,
                    "task_type": "raft_distractor",
                    "gold_chunk_ids": [],
                    "metadata": {
                        "qa_id": record.get("query_id"),
                        "gold_cids": positive_cids,
                        "source": "yuitc",
                    },
                }
            )

    final_records = _mix_by_ratio(positives, negatives, positive_ratio=active_config.positive_ratio)
    ensure_dir("data/aligned")
    save_jsonl(active_config.output_path, final_records)
    return final_records


def _select_raft_distractors(anchor: dict, corpus_records: list[dict], limit: int, anchor_index: int = 0) -> list[dict]:
    if limit <= 0 or not corpus_records:
        return []
    question = str(anchor.get("question", ""))
    gold_cids = {str(cid) for cid in anchor.get("positive_cids", [])}
    candidate_limit = min(len(corpus_records), max(limit * 24, 96))
    candidates: list[tuple[float, dict]] = []

    # Bounded circular scan keeps the builder O(n) for large YuITC runs while
    # still drawing nearby and varied distractors from the same dataset split.
    for offset in range(1, candidate_limit + 1):
        candidate = corpus_records[(anchor_index + offset) % len(corpus_records)]
        candidate_cids = {str(cid) for cid in candidate.get("positive_cids", [])}
        if not candidate_cids or gold_cids.intersection(candidate_cids):
            continue
        text = str(candidate.get("positive_context", "")).strip()
        if not text:
            continue
        score = keyword_coverage_score(question, text) + direct_answer_score(question, text)
        candidates.append((score, candidate))

    candidates.sort(key=lambda item: item[0], reverse=True)
    distractors: list[dict] = []
    seen: set[str] = set()
    for _, candidate in candidates:
        context = str(candidate.get("positive_context", "")).strip()
        if context in seen:
            continue
        seen.add(context)
        cids = [str(cid) for cid in candidate.get("positive_cids", []) if str(cid).strip()]
        distractors.append(
            _to_context_record(
                {
                    "chunk_id": str(candidate.get("positive_chunk_id") or f"yuitc:{candidate.get('query_id', len(seen))}:neg"),
                    "cid": cids[0] if cids else "",
                    "text": context,
                    "doc_name": candidate.get("doc_name", ""),
                },
                is_gold=False,
            )
        )
        if len(distractors) >= limit:
            break
    return distractors


def _build_concise_raft_target(question: str, positive_context: str, context: dict) -> str:
    sentences = split_sentences(positive_context)
    ranked = sorted(
        unique_preserve_order(sentences),
        key=lambda sentence: direct_answer_score(question, sentence) + keyword_coverage_score(question, sentence),
        reverse=True,
    )
    answer = (ranked[0] if ranked else positive_context).strip()
    basis = _format_context_basis(context)
    return "\n".join(
        [
            f"Tra loi: {answer}",
            f"Can cu: {basis}.",
            "Lap luan: Can cu tren khop voi noi dung cau hoi; vi vay ket luan chi duoc rut ra tu evidence nay.",
            "Thong tin con thieu: Khong co them thong tin can bo sung neu chi dua tren evidence hien co.",
        ]
    ).strip()


def _format_context_basis(context: dict) -> str:
    parts = [str(context.get("doc_name") or "Van ban phap ly").strip()]
    if context.get("article"):
        parts.append(f"Dieu {context.get('article')}")
    if context.get("clause"):
        parts.append(f"Khoan {context.get('clause')}")
    if context.get("cid"):
        parts.append(f"cid={context.get('cid')}")
    if context.get("chunk_id"):
        parts.append(f"chunk_id={context.get('chunk_id')}")
    return " - ".join(part for part in parts if part)


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
