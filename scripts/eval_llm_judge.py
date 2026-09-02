from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import scripts._bootstrap as _bootstrap

from scripts.eval_answer_generation import _load_llm

JUDGE_SYSTEM = (
    "Bạn là giám khảo đánh giá chất lượng câu trả lời pháp lý của một hệ thống RAG. "
    "Bạn được cung cấp: câu hỏi, các điều khoản (trích dẫn để làm bằng chứng), và câu trả lời của hệ thống. "
    "Hãy đánh giá theo thang 1-5 (5 = xuất sắc, 1 = rất kém) cho từng tiêu chí. "
    'Chỉ trả về JSON với key: "legal_correctness", "grounding", "citation_correctness", "directness", "support_ratio" (0-1). '
    "support_ratio = tỷ lệ phần khẳng định trong câu trả lời được hỗ trợ bởi bằng chứng được cung cấp."
)


def build_judge_messages(question: str, prediction: str, evidence: str, tokenizer) -> str:
    user = (
        "CÂU HỎI:\n{question}\n\n"
        "BẰNG CHỨNG (các điều khoản/pháp lý liên quan):\n{evidence}\n\n"
        "CÂU TRẢ LỜI CỦA HỆ THỐNG:\n{prediction}\n\n"
        "Hãy đánh giá 5 tiêu chí trên và trả về JSON."
    ).format(question=question, prediction=prediction, evidence=evidence)
    messages = [
        {"role": "system", "content": JUDGE_SYSTEM},
        {"role": "user", "content": user},
    ]
    return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)


def parse_judge_output(text: str) -> dict:
    text = str(text or "")
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}


def _evidence_from_detail(detail: dict) -> str:
    retrieval = detail.get("retrieval") or {}
    retrieved = retrieval.get("retrieved") or []
    parts = [
        f"[{item.get('rank')}] (cid={item.get('cid')}) {str(item.get('snippet', '')).strip()}"
        for item in retrieved[:5]
    ]
    return "\n\n".join(parts) if parts else "(không có bằng chứng)"


def run_judge(model, tokenizer, prompt: str, max_new_tokens: int = 64) -> str:
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


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM-as-judge evaluation of citation correctness and grounding.")
    parser.add_argument("--report", default="reports/answer_generation_qwen_qlora_retrieved_report.json")
    parser.add_argument("--base-model", default="Qwen/Qwen2.5-7B-Instruct")
    parser.add_argument("--adapter", default="models/qwen2.5-7b-legalqa-qlora")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--max-new-tokens", type=int, default=64)
    parser.add_argument("--report-dir", default="reports")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    details = report.get("details") or []
    if args.limit:
        details = details[: args.limit]

    class _Args:
        base_model = args.base_model
        adapter = args.adapter

    model_cache: dict = {}
    tokenizer, model = _load_llm(_Args(), "qwen_qlora", model_cache)

    judged = []
    proxy_correct_total = 0
    judge_correct_total = 0
    agreements = 0
    for index, detail in enumerate(details):
        question = str(detail.get("question", ""))
        prediction = str(detail.get("prediction_text", detail.get("prediction", ""))).strip()
        evidence = _evidence_from_detail(detail)
        prompt = build_judge_messages(question, prediction, evidence, tokenizer)
        verdict = parse_judge_output(generate(model, tokenizer, prompt, args.max_new_tokens))

        proxy = float(detail.get("citation_correctness", 0.0) or 0.0)
        judge_correct = float(verdict.get("citation_correctness", 0.0) or 0.0) / 5.0
        agreements += int((judge_correct >= 0.5) == (proxy >= 0.5))
        proxy_correct_total += int(proxy >= 0.5)
        judge_correct_total += int(judge_correct >= 0.5)

        judged.append(
            {
                "sample_index": index,
                "question": question,
                "prediction": prediction,
                "evidence": evidence,
                "proxy_citation_correctness": proxy,
                "judge_verdict": verdict,
                "judge_citation_correctness": judge_correct,
                "judge_support_ratio": float(verdict.get("support_ratio", judge_correct)),
            }
        )

    n = len(judged)
    mean = lambda key: round(sum(float(item["judge_verdict"].get(key, 0.0) or 0.0) for item in judged) / max(n, 1), 4)
    mean_support = round(sum(item["judge_support_ratio"] for item in judged) / max(n, 1), 4)
    payload = {
        "samples": n,
        "source_report": args.report,
        "judge_model": args.base_model,
        "judge_adapter": args.adapter,
        "metrics": {
            "judge_legal_correctness": mean("legal_correctness"),
            "judge_grounding": mean("grounding"),
            "judge_citation_correctness": mean("citation_correctness"),
            "judge_directness": mean("directness"),
            "judge_support_ratio": mean_support,
            "proxy_citation_correctness_high_rate": round(proxy_correct_total / max(n, 1), 4),
            "judge_citation_correctness_high_rate": round(judge_correct_total / max(n, 1), 4),
            "coarse_agreement_with_proxy": round(agreements / max(n, 1), 4),
        },
        "verdicts": judged,
    }
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    out_json = report_dir / "llm_judge_report.json"
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"samples": n, "metrics": payload["metrics"]}, ensure_ascii=False, indent=2))
    print(f"Saved: {out_json}")


if __name__ == "__main__":
    main()
