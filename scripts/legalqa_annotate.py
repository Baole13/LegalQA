from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

import scripts._bootstrap as _bootstrap

from src.utils.io import save_json

ANNOTATOR_SYSTEM = (
    "Bạn là người chấm điểm chất lượng câu trả lời pháp lý của một hệ thống RAG "
    "(LLM-as-annotator). Bạn được cung cấp: câu hỏi, câu trả lời đúng (gold), câu trả lời "
    "của hệ thống, và bằng chứng pháp lý đã được truy hồi. Hãy đánh giá TỪNG tiêu chí sau "
    "theo thang 1-5 (5 = xuất sắc, 1 = rất kém), dựa vào bằng chứng đã cho chứ không dựa vào gold:\n"
    "1. legal_correctness: câu trả lời có đúng về mặt pháp lý không (khớp với bằng chứng/văn bản luật hiện hành).\n"
    "2. grounding: mọi khẳng định có được dựa trên bằng chứng đã cho không (không bịa).\n"
    "3. citation_correctness: trích dẫn điều/khoản có thực sự GOVERN khẳng định được dùng không, hay chỉ là trích dẫn cho có.\n"
    "4. directness: câu trả lời có trực tiếp giải đáp câu hỏi không (không lan man, không ngoài lề).\n"
    "5. refusal_quality: nếu câu hỏi mơ hồ/ngoài phạm vi/khiếm khuyết bằng chứng, hệ thống có từ chối phù hợp không "
    "(5 = từ chối đúng và rõ ràng, 3 = trả lời dù yếu bằng chứng, 1 = trả lời bừa/đoán).\n"
    "Chỉ trả về một JSON hợp lệ với đúng các key: "
    '{"legal_correctness": 1-5, "grounding": 1-5, "citation_correctness": 1-5, "directness": 1-5, "refusal_quality": 1-5}'
    " Không thêm chú thích ngoài JSON."
)


def build_annotator_messages(
    question: str, gold_answer: str, prediction: str, evidence: str, tokenizer
) -> str:
    user = (
        "CÂU HỎI:\n{question}\n\n"
        "BẰNG CHỨNG (văn bản pháp lý đã truy hồi):\n{evidence}\n\n"
        "CÂU TRẢ LỜI CỦA HỆ THỐNG:\n{prediction}\n\n"
        "CÂU TRẢ LỜI MẪU (gold, chỉ để tham khảo):\n{gold}\n\n"
        "Hãy chấm 5 tiêu chí (1-5) và trả về JSON duy nhất."
    ).format(question=question, gold=gold_answer, prediction=prediction, evidence=evidence)
    messages = [
        {"role": "system", "content": ANNOTATOR_SYSTEM},
        {"role": "user", "content": user},
    ]
    return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)


_KEY_NORMALIZE = {
    "legal_correctness": "legal_correctness",
    "grounding": "grounding",
    "citation_correctness": "citation_correctness",
    "citation_correctity": "citation_correctness",
    "citation_correct": "citation_correctness",
    "citation_correctness_score": "citation_correctness",
    "directness": "directness",
    "directnes": "directness",
    "refusal_quality": "refusal_quality",
    "refusal": "refusal_quality",
}


def parse_annotator_output(text: str) -> dict:
    text = str(text or "")
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {}
    try:
        raw = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    return {_KEY_NORMALIZE.get(k, k): v for k, v in raw.items() if _KEY_NORMALIZE.get(k, k) in _KEY_NORMALIZE}


def run_annotator(model, tokenizer, prompt: str, max_new_tokens: int = 128) -> str:
    import torch

    inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=4096).to(model.device)
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            eos_token_id=tokenizer.eos_token_id,
            pad_token_id=tokenizer.pad_token_id,
        )
    generated = outputs[0][inputs["input_ids"].shape[1]:]
    return tokenizer.decode(generated, skip_special_tokens=True)


def infer_evidence(row: dict) -> str:
    raw = row.get("retrieved_evidence") or ""
    if str(raw).strip():
        return str(raw)
    prediction = str(row.get("prediction", ""))
    found = re.findall(r"(Điều\s+\d+(?:[a-z]|(?:,\s*Khoản\s+\d+))?)", prediction, re.IGNORECASE)
    return "Trích từ câu trả lời: " + ", ".join(dict.fromkeys(found)) if found else "(không có bằng chứng được cung cấp)"


def clamp_score(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return ""
    if f < 1 or f > 5 or f != int(f):
        return ""
    return str(int(f))


def main() -> None:
    parser = argparse.ArgumentParser(description="AI-assisted annotation of human-eval samples (single annotator).")
    parser.add_argument("--input", required=True, help="CSV/TSV sample file to annotate")
    parser.add_argument("--base-model", default="Qwen/Qwen2.5-7B-Instruct")
    parser.add_argument("--adapter", default="")
    parser.add_argument("--limit", type=int, default=0, help="0 = all rows")
    parser.add_argument("--max-new-tokens", type=int, default=128)
    parser.add_argument("--notes", default="AI-assisted (single LLM annotator, no inter-annotator agreement)")
    args = parser.parse_args()

    input_path = Path(args.input)
    suffix = input_path.suffix.lower()
    if suffix == ".tsv":
        with input_path.open("r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            rows = list(reader)
    else:
        with input_path.open("r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
    if args.limit:
        rows = rows[: args.limit]

    from scripts.eval_answer_generation import _load_llm

    class _Args:
        base_model = args.base_model
        adapter = args.adapter

    tokenizer, model = _load_llm(_Args(), "annotator", {})

    metrics = []
    for row in rows:
        row["a1_notes"] = args.notes
        for key in ("a1_legal_correctness", "a1_grounding", "a1_citation_correctness", "a1_directness", "a1_refusal"):
            row[key] = ""
        question = str(row.get("question", ""))
        gold = str(row.get("gold_answer", ""))
        prediction = str(row.get("prediction", ""))
        evidence = infer_evidence(row)
        prompt = build_annotator_messages(question, gold, prediction, evidence, tokenizer)
        verdict = parse_annotator_output(run_annotator(model, tokenizer, prompt, args.max_new_tokens))
        row["a1_legal_correctness"] = clamp_score(verdict.get("legal_correctness"))
        row["a1_grounding"] = clamp_score(verdict.get("grounding"))
        row["a1_citation_correctness"] = clamp_score(verdict.get("citation_correctness"))
        row["a1_directness"] = clamp_score(verdict.get("directness"))
        row["a1_refusal"] = clamp_score(verdict.get("refusal_quality"))
        metrics.append(
            {
                "question": question,
                **{k: clamp_score(verdict.get(k)) for k in ("legal_correctness", "grounding", "citation_correctness", "directness", "refusal_quality")},
                "raw": verdict,
            }
        )

    if suffix == ".tsv":
        with input_path.open("w", encoding="utf-8", newline="") as handle:
            fieldnames = list(rows[0].keys())
            writer = csv.DictWriter(handle, delimiter="\t", fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    else:
        with input_path.open("w", encoding="utf-8", newline="") as handle:
            fieldnames = list(rows[0].keys())
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    report_dir = input_path.parent
    stem = input_path.stem
    out = report_dir / f"{stem}_ai_annotation.json"
    n = len(metrics)
    out.write_text(
        json.dumps(
            {
                "source": str(input_path),
                "annotator_type": "ai_single_llm",
                "annotators": 1,
                "independent": False,
                "ai_assisted": True,
                "base_model": args.base_model,
                "adapter": args.adapter or None,
                "samples": n,
                "metrics": {m: round(sum(float(x[m] or 0) for x in metrics) / max(n, 1), 4) for m in ("legal_correctness", "grounding", "citation_correctness", "directness", "refusal_quality")},
                "per_sample": metrics,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Annotated {n} rows -> {input_path}")
    print(f"Per-sample detail: {out}")


if __name__ == "__main__":
    main()