from __future__ import annotations

import argparse
import json
from pathlib import Path

import _bootstrap

from src.evaluation.answer_eval import evaluate_answer_generation, load_answer_eval_samples


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate answer generation quality on LegalQA SFT test data.")
    parser.add_argument(
        "--dataset",
        default="data/processed/thangvip_legalqa/test.jsonl",
        help="Path to the SFT test split or similar jsonl file.",
    )
    parser.add_argument(
        "--base-model",
        default="Qwen/Qwen2.5-7B-Instruct",
        help="Base model name or path.",
    )
    parser.add_argument(
        "--adapter",
        default="models/qwen2.5-7b-legalqa-qlora",
        help="LoRA adapter path.",
    )
    parser.add_argument("--limit", type=int, default=50, help="Max number of samples.")
    parser.add_argument("--max-new-tokens", type=int, default=256, help="Generation length.")
    parser.add_argument(
        "--report-dir",
        default="reports",
        help="Directory to write report json/md files.",
    )
    args = parser.parse_args()

    try:
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("Missing inference dependencies. Install requirements-runpod.txt first.") from exc

    adapter_path = Path(args.adapter)
    if not adapter_path.exists():
        raise SystemExit(f"Adapter path not found: {adapter_path}")

    samples = load_answer_eval_samples(args.dataset, limit=args.limit)
    if not samples:
        raise SystemExit(f"No evaluation samples found in {args.dataset}")

    tokenizer = AutoTokenizer.from_pretrained(args.base_model, trust_remote_code=False)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        dtype=getattr(torch, "bfloat16", torch.float16),
        device_map="auto",
        trust_remote_code=False,
    )
    model = PeftModel.from_pretrained(model, str(adapter_path))
    model.eval()

    def generate_fn(sample):
        inputs = tokenizer(sample.prompt, return_tensors="pt").to(model.device)
        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=int(args.max_new_tokens),
                do_sample=False,
                eos_token_id=tokenizer.eos_token_id,
                pad_token_id=tokenizer.pad_token_id,
            )
        generated = outputs[0][inputs["input_ids"].shape[-1] :]
        return tokenizer.decode(generated, skip_special_tokens=True).strip()

    metrics = evaluate_answer_generation(samples, generate_fn)
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    report_json = report_dir / "answer_generation_report.json"
    report_md = report_dir / "answer_generation_report.md"
    report_json.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    report_md.write_text(_render_markdown(metrics), encoding="utf-8")

    print(json.dumps({k: v for k, v in metrics.items() if k != "details"}, ensure_ascii=False, indent=2))
    print(f"Saved: {report_json}")
    print(f"Saved: {report_md}")


def _render_markdown(metrics: dict) -> str:
    lines = [
        "# Answer Generation Report",
        "",
        f"- Samples: {metrics.get('samples', 0)}",
        f"- Exact Match: {metrics.get('exact_match', 0.0)}",
        f"- Token F1: {metrics.get('token_f1', 0.0)}",
        f"- ROUGE-L: {metrics.get('rouge_l', 0.0)}",
        f"- Citation Presence: {metrics.get('citation_presence', 0.0)}",
        f"- Structure Score: {metrics.get('structure_score', 0.0)}",
        f"- Faithfulness Score: {metrics.get('faithfulness_score', 0.0)}",
        f"- Reasoning Score: {metrics.get('reasoning_score', 0.0)}",
        f"- Directness Score: {metrics.get('directness_score', 0.0)}",
        f"- Citation Correctness: {metrics.get('citation_correctness', 0.0)}",
        f"- Refusal Quality: {metrics.get('refusal_quality', 0.0)}",
        f"- Avg Prediction Length: {metrics.get('avg_prediction_length', 0.0)}",
        f"- Avg Gold Length: {metrics.get('avg_gold_length', 0.0)}",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
