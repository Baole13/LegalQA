from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from src.training.data import load_training_records
from src.utils.text import normalize_text, strip_accents, tokenize


REQUIRED_FIELDS = ("answer", "legal_basis", "reasoning", "missing_info", "confidence")
LEGACY_REQUIRED_SECTIONS = (
    "Can cu phap ly:",
    "Dieu kien phap ly lien quan:",
    "Ap dung vao tinh huong:",
    "Ket luan:",
    "Thong tin con thieu:",
)


@dataclass(frozen=True)
class AnswerEvalSample:
    question: str
    context: str
    gold_answer: str
    prompt: str
    metadata: dict


def load_answer_eval_samples(path: str | Path, limit: int = 0) -> list[AnswerEvalSample]:
    records = load_training_records(path, max_samples=limit)
    samples: list[AnswerEvalSample] = []
    for record in records:
        sample = _record_to_sample(record)
        if sample is None:
            continue
        samples.append(sample)
    return samples


def _record_to_sample(record: dict) -> AnswerEvalSample | None:
    messages = record.get("messages") or []
    if not messages:
        return None
    user_message = next((item for item in messages if item.get("role") == "user"), None)
    assistant_message = next((item for item in messages if item.get("role") == "assistant"), None)
    if not user_message or not assistant_message:
        return None
    question, context = _parse_user_prompt(str(user_message.get("content", "")))
    gold_answer = str(assistant_message.get("content", "")).strip()
    if not question or not gold_answer:
        return None
    prompt = "\n\n".join(
        f"{msg['role'].capitalize()}: {msg['content']}"
        for msg in messages
        if msg.get("role") != "assistant"
    )
    return AnswerEvalSample(
        question=question,
        context=context,
        gold_answer=gold_answer,
        prompt=prompt,
        metadata=record.get("metadata") or {},
    )


def _parse_user_prompt(prompt: str) -> tuple[str, str]:
    context = _extract_block(prompt, "Van ban phap ly:", "Cau hoi:")
    question = _extract_block(prompt, "Cau hoi:", "Yeu cau:")
    return question.strip(), context.strip()


def _extract_block(text: str, start: str, end: str) -> str:
    start_index = text.find(start)
    if start_index < 0:
        return ""
    start_index += len(start)
    end_index = text.find(end, start_index)
    if end_index < 0:
        return text[start_index:].strip()
    return text[start_index:end_index].strip()


def evaluate_answer_generation(
    samples: Iterable[AnswerEvalSample],
    generate_fn,
) -> dict:
    sample_results: list[dict] = []
    for sample in samples:
        predicted = generate_fn(sample)
        sample_results.append(_score_sample(sample, predicted))

    if not sample_results:
        return {
            "samples": 0,
            "exact_match": 0.0,
            "token_f1": 0.0,
            "rouge_l": 0.0,
            "citation_presence": 0.0,
            "structure_score": 0.0,
            "faithfulness_score": 0.0,
            "reasoning_score": 0.0,
            "directness_score": 0.0,
            "citation_correctness": 0.0,
            "refusal_quality": 0.0,
            "avg_prediction_length": 0.0,
            "avg_gold_length": 0.0,
            "details": [],
        }

    total = len(sample_results)
    metrics = {
        "samples": total,
        "exact_match": round(sum(item["exact_match"] for item in sample_results) / total, 4),
        "token_f1": round(sum(item["token_f1"] for item in sample_results) / total, 4),
        "rouge_l": round(sum(item["rouge_l"] for item in sample_results) / total, 4),
        "citation_presence": round(sum(item["citation_presence"] for item in sample_results) / total, 4),
        "structure_score": round(sum(item["structure_score"] for item in sample_results) / total, 4),
        "faithfulness_score": round(sum(item["faithfulness_score"] for item in sample_results) / total, 4),
        "reasoning_score": round(sum(item["reasoning_score"] for item in sample_results) / total, 4),
        "directness_score": round(sum(item["directness_score"] for item in sample_results) / total, 4),
        "citation_correctness": round(sum(item["citation_correctness"] for item in sample_results) / total, 4),
        "refusal_quality": round(sum(item["refusal_quality"] for item in sample_results) / total, 4),
        "avg_prediction_length": round(sum(item["prediction_length"] for item in sample_results) / total, 2),
        "avg_gold_length": round(sum(item["gold_length"] for item in sample_results) / total, 2),
        "details": sample_results,
    }
    return metrics


def _score_sample(sample: AnswerEvalSample, predicted: object) -> dict:
    prediction_payload = _coerce_prediction(predicted)
    predicted_text = prediction_payload["text"]
    gold = sample.gold_answer
    normalized_pred = _normalize(predicted_text)
    normalized_gold = _normalize(gold)
    context = sample.context
    return {
        "question": sample.question,
        "prediction": predicted,
        "prediction_text": predicted_text,
        "gold_answer": gold,
        "exact_match": 1.0 if normalized_pred == normalized_gold else 0.0,
        "token_f1": round(_token_f1(gold, predicted_text), 4),
        "rouge_l": round(_rouge_l_f1(gold, predicted_text), 4),
        "citation_presence": 1.0 if _has_citation_marker(predicted_text) or prediction_payload["citations"] else 0.0,
        "structure_score": round(_structure_score(predicted), 4),
        "faithfulness_score": round(_faithfulness_score(predicted_text, context), 4),
        "reasoning_score": round(_reasoning_score(predicted), 4),
        "directness_score": round(_directness_score(sample.question, prediction_payload["answer"]), 4),
        "citation_correctness": round(_citation_correctness(prediction_payload, context), 4),
        "refusal_quality": round(_refusal_quality(prediction_payload, context), 4),
        "prediction_length": len(predicted_text),
        "gold_length": len(gold),
    }


def _coerce_prediction(predicted: object) -> dict:
    if isinstance(predicted, dict):
        answer = str(predicted.get("answer", "")).strip()
        legal_basis = predicted.get("legal_basis") or []
        reasoning = str(predicted.get("reasoning", "")).strip()
        missing_info = predicted.get("missing_info") or []
        citations = predicted.get("citations") or []
        text = "\n".join(
            part
            for part in [
                answer,
                "\n".join(str(item) for item in legal_basis),
                reasoning,
                "\n".join(str(item) for item in missing_info),
            ]
            if part
        ).strip()
        return {
            "answer": answer,
            "legal_basis": legal_basis,
            "reasoning": reasoning,
            "missing_info": missing_info,
            "citations": citations,
            "confidence": predicted.get("confidence"),
            "text": text,
        }
    text = str(predicted).strip()
    return {
        "answer": _extract_legacy_answer(text),
        "legal_basis": [],
        "reasoning": text,
        "missing_info": [],
        "citations": [],
        "confidence": None,
        "text": text,
    }


def _normalize(text: str) -> str:
    return strip_accents(normalize_text(text)).lower()


def _token_f1(gold: str, pred: str) -> float:
    gold_tokens = tokenize(gold)
    pred_tokens = tokenize(pred)
    if not gold_tokens or not pred_tokens:
        return 0.0
    gold_counts = {}
    for token in gold_tokens:
        gold_counts[token] = gold_counts.get(token, 0) + 1
    overlap = 0
    for token in pred_tokens:
        count = gold_counts.get(token, 0)
        if count > 0:
            overlap += 1
            gold_counts[token] = count - 1
    precision = overlap / len(pred_tokens)
    recall = overlap / len(gold_tokens)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _rouge_l_f1(gold: str, pred: str) -> float:
    ref = tokenize(gold)
    hyp = tokenize(pred)
    if not ref or not hyp:
        return 0.0
    lcs = _lcs_length(ref, hyp)
    precision = lcs / len(hyp)
    recall = lcs / len(ref)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _lcs_length(a: list[str], b: list[str]) -> int:
    dp = [0] * (len(b) + 1)
    for token_a in a:
        prev = 0
        for j, token_b in enumerate(b, start=1):
            temp = dp[j]
            if token_a == token_b:
                dp[j] = prev + 1
            else:
                dp[j] = max(dp[j], dp[j - 1])
            prev = temp
    return dp[-1]


def _has_citation_marker(text: str) -> bool:
    normalized = _normalize(text)
    return any(marker in normalized for marker in ("dieu ", "khoan ", "[", "can cu phap ly"))


def _structure_score(predicted: object) -> float:
    if isinstance(predicted, dict):
        hits = 0
        for field in REQUIRED_FIELDS:
            value = predicted.get(field)
            if isinstance(value, list):
                hits += 1 if any(str(item).strip() for item in value) else 0
            elif str(value or "").strip():
                hits += 1
        return hits / len(REQUIRED_FIELDS)
    normalized = _normalize(str(predicted))
    hits = sum(1 for section in LEGACY_REQUIRED_SECTIONS if _normalize(section) in normalized)
    return hits / len(LEGACY_REQUIRED_SECTIONS)


def _faithfulness_score(text: str, context: str) -> float:
    if not text or not context:
        return 0.0
    text_tokens = tokenize(text)
    context_tokens = set(tokenize(context))
    if not text_tokens:
        return 0.0
    overlap = sum(1 for token in text_tokens if token in context_tokens)
    lexical_support = overlap / len(text_tokens)
    citation_bonus = 0.25 if _has_citation_marker(text) else 0.0
    return min(1.0, lexical_support * 0.75 + citation_bonus)


def _reasoning_score(predicted: object) -> float:
    payload = _coerce_prediction(predicted)
    normalized = _normalize(payload["text"])
    logic_markers = ("do do", "vi vay", "theo do", "tu do", "suy ra", "neu", "neu khong", "boi vi")
    section_score = _structure_score(predicted)
    logic_score = sum(1 for marker in logic_markers if marker in normalized) / len(logic_markers)
    missing_info_score = 1.0 if payload["missing_info"] or ("thong tin con thieu" in normalized and ("khong co" in normalized or "can bo sung" in normalized)) else 0.0
    citation_score = 1.0 if payload["citations"] or _has_citation_marker(payload["text"]) else 0.0
    return min(1.0, (section_score * 0.4) + (logic_score * 0.25) + (missing_info_score * 0.15) + (citation_score * 0.2))


def _extract_legacy_answer(text: str) -> str:
    normalized_lines = [line.strip("- ").strip() for line in text.splitlines()]
    if "Ket luan:" in normalized_lines:
        index = normalized_lines.index("Ket luan:")
        for line in normalized_lines[index + 1 :]:
            if line and not line.endswith(":"):
                return line
    return text.splitlines()[0].strip() if text.splitlines() else ""


def _directness_score(question: str, answer: str) -> float:
    if not answer:
        return 0.0
    normalized_question = _normalize(question)
    normalized_answer = _normalize(answer)
    direct_markers = ("bao nhieu", "ai ", "co ", "khong", "duoc", "phai")
    if not any(marker in normalized_question for marker in direct_markers):
        return 1.0 if len(answer) <= 700 else 0.5
    if normalized_answer.startswith(("co", "khong", "toi khong biet")):
        return 1.0
    answer_tokens = tokenize(answer)
    return 1.0 if answer_tokens and len(answer_tokens) <= 80 else 0.5


def _citation_correctness(payload: dict, context: str) -> float:
    citations = payload.get("citations") or []
    if citations:
        context_norm = _normalize(context)
        hits = 0
        for citation in citations:
            cid = str(citation.get("cid") or citation.get("chunk_id") or "").strip()
            label = str(citation.get("label") or "").strip()
            if cid and cid in context:
                hits += 1
            elif label and any(token in context_norm for token in tokenize(label)[:4]):
                hits += 1
        return hits / max(len(citations), 1)
    return 1.0 if _has_citation_marker(payload.get("text", "")) else 0.0


def _refusal_quality(payload: dict, context: str) -> float:
    answer = _normalize(payload.get("answer", ""))
    refused = answer.startswith("toi khong biet") or "khong du can cu" in answer
    if not refused:
        return 1.0
    context_tokens = tokenize(context)
    return 1.0 if len(context_tokens) < 20 else 0.5
