from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import scripts._bootstrap as _bootstrap

from src.evaluation.answer_eval import AnswerEvalSample, evaluate_answer_generation, load_answer_eval_samples, render_eval_prompt
from src.qa.context_builder import build_context
from src.qa.generator import ExtractiveAnswerGenerator
from src.qa.pipeline import LegalQAPipeline

LLM_VARIANTS = {"qwen_prompt_only", "qwen_qlora", "qlora", "oracle_evidence_qwen"}
BASELINE_VARIANTS = ("extractive_only", "qwen_prompt_only", "qwen_qlora", "oracle_evidence_qwen")


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
        "--prompt-style",
        choices=("default", "schema"),
        default="default",
        help="Prompt rendering style. Use schema to request JSON-formatted answers.",
    )
    parser.add_argument(
        "--variant",
        choices=("extractive_only", "qwen_prompt_only", "qwen_qlora", "qlora", "oracle_evidence_qwen", "all_baselines"),
        default="qwen_qlora",
        help="Generation variant to evaluate. 'qlora' is an alias for qwen_qlora.",
    )
    parser.add_argument(
        "--report-dir",
        default="reports",
        help="Directory to write report json/md files.",
    )
    parser.add_argument(
        "--evidence-mode",
        choices=("oracle_context", "retrieved_context"),
        default="oracle_context",
        help="Use oracle/SFT context from the dataset or retrieve evidence with the RAG pipeline before generation.",
    )
    parser.add_argument("--retrieval-top-k", type=int, default=5, help="Number of retrieved chunks to place in the generation context.")
    parser.add_argument(
        "--retrieval-variant",
        choices=("full_with_cross_encoder_reranker",),
        default="full_with_cross_encoder_reranker",
        help="Retrieval variant used when --evidence-mode retrieved_context is selected.",
    )
    args = parser.parse_args()

    samples = load_answer_eval_samples(args.dataset, limit=args.limit)
    if not samples:
        raise SystemExit(f"No evaluation samples found in {args.dataset}")

    retrieval_metadata: list[dict] = []
    if args.evidence_mode == "retrieved_context":
        samples, retrieval_metadata = _replace_with_retrieved_context(samples, top_k=args.retrieval_top_k)

    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    if args.variant == "all_baselines":
        reports = []
        model_cache = {}
        for variant in BASELINE_VARIANTS:
            metrics = _evaluate_variant(args, samples, variant, model_cache=model_cache, retrieval_metadata=retrieval_metadata)
            reports.append({k: v for k, v in metrics.items() if k != "details"})
        reports = _annotate_baseline_distinctness(reports)
        payload = {"samples": len(samples), "limit": args.limit, "evidence_mode": args.evidence_mode, "baselines": reports}
        report_json = report_dir / "generation_baselines_report.json"
        report_md = report_dir / "generation_baselines_report.md"
        report_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        report_md.write_text(_render_baselines_markdown(payload), encoding="utf-8")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print(f"Saved: {report_json}")
        print(f"Saved: {report_md}")
        return

    variant = _normalize_variant(args.variant)
    metrics = _evaluate_variant(args, samples, variant, model_cache={}, retrieval_metadata=retrieval_metadata)
    report_json = report_dir / "answer_generation_report.json"
    report_md = report_dir / "answer_generation_report.md"
    if args.evidence_mode == "retrieved_context":
        style_suffix = "_schema" if args.prompt_style == "schema" else ""
        report_json = report_dir / f"answer_generation_{variant}_retrieved{style_suffix}_report.json"
        report_md = report_dir / f"answer_generation_{variant}_retrieved{style_suffix}_report.md"
    elif variant != "qwen_qlora":
        report_json = report_dir / f"answer_generation_{variant}_report.json"
        report_md = report_dir / f"answer_generation_{variant}_report.md"
    report_json.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    report_md.write_text(_render_markdown(metrics), encoding="utf-8")

    print(json.dumps({k: v for k, v in metrics.items() if k != "details"}, ensure_ascii=False, indent=2))
    print(f"Saved: {report_json}")
    print(f"Saved: {report_md}")


def _normalize_variant(variant: str) -> str:
    return "qwen_qlora" if variant == "qlora" else variant


def _evaluate_variant(args, samples, variant: str, model_cache: dict, retrieval_metadata: list[dict] | None = None) -> dict:
    variant = _normalize_variant(variant)
    if variant == "extractive_only":
        generator = ExtractiveAnswerGenerator()

        def generate_fn(sample):
            evidence = _sample_context_as_evidence(sample)
            return generator.generate(sample.question, evidence)

    elif variant in LLM_VARIANTS:
        tokenizer, model = _load_llm(args, variant, model_cache)
        input_fingerprint = _prompt_fingerprint(samples, tokenizer, prompt_style=getattr(args, "prompt_style", "default"))

        def generate_fn(sample):
            prompt = _render_prompt(sample, tokenizer=tokenizer, prompt_style=getattr(args, "prompt_style", "default"))
            inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
            try:
                import torch
            except ImportError as exc:  # pragma: no cover
                raise SystemExit("Missing torch for LLM inference.") from exc
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

    else:  # pragma: no cover
        raise SystemExit(f"Unsupported variant: {variant}")

    metrics = evaluate_answer_generation(samples, generate_fn)
    if retrieval_metadata:
        _attach_retrieval_metadata(metrics, retrieval_metadata)
    metrics["variant"] = variant
    metrics["dataset"] = args.dataset
    metrics["base_model"] = args.base_model if variant != "extractive_only" else None
    metrics["adapter"] = args.adapter if variant == "qwen_qlora" else None
    metrics["evidence_mode"] = _evidence_mode(variant, getattr(args, "evidence_mode", "oracle_context"))
    metrics["baseline_note"] = _baseline_note(variant, getattr(args, "evidence_mode", "oracle_context"))
    metrics["prompt_style"] = getattr(args, "prompt_style", "default")
    if getattr(args, "evidence_mode", "oracle_context") == "retrieved_context":
        metrics["retrieval_variant"] = args.retrieval_variant
        metrics["retrieval_top_k"] = args.retrieval_top_k
    if variant in LLM_VARIANTS:
        metrics["input_fingerprint"] = input_fingerprint
    return metrics


def _evidence_mode(variant: str, evidence_mode: str = "oracle_context") -> str:
    if evidence_mode == "retrieved_context":
        if variant == "extractive_only":
            return "retrieved_context_extractive"
        return "retrieved_context_llm"
    if variant == "extractive_only":
        return "oracle_sft_context_extractive"
    if variant == "oracle_evidence_qwen":
        return "oracle_sft_context_llm"
    return "sft_prompt_context"


def _baseline_note(variant: str, evidence_mode: str = "oracle_context") -> str:
    if evidence_mode == "retrieved_context":
        if variant == "extractive_only":
            return "Extractive generator over retrieved cross-encoder reranked context; no LLM inference."
        return "LLM generation over retrieved cross-encoder reranked context."
    if variant == "oracle_evidence_qwen":
        return "The current SFT evaluation prompt already contains oracle/gold context; interpret this as oracle-context generation, not retrieved-context generation."
    if variant == "qwen_prompt_only":
        return "Base Qwen with the same evaluation prompt/context as the main QLoRA run, without adapter."
    if variant == "extractive_only":
        return "Extractive generator over oracle/SFT context; no LLM inference."
    return "Base Qwen plus LegalQA QLoRA adapter."


SCHEMA_PROMPT_INSTRUCTION = """Return only valid JSON with exactly these keys:
- answer: a concise direct answer in Vietnamese.
- legal_basis: an array of cited legal provisions or chunk IDs that support the answer.
- reasoning: a short explanation grounded only in the provided evidence.
- missing_info: an array of missing facts or evidence, or an empty array if none.
- citations: an array of objects with chunk_id or cid and a short supporting quote.
- confidence: one of high, medium, low.
Do not include Markdown fences, chat prefixes, or text outside the JSON object."""


def _render_prompt(sample, tokenizer=None, prompt_style: str = "default") -> str:
    if prompt_style != "schema":
        return render_eval_prompt(sample, tokenizer=tokenizer)
    messages = [dict(item) for item in sample.messages if item.get("role") != "assistant"]
    if messages:
        user_indexes = [idx for idx, message in enumerate(messages) if message.get("role") == "user"]
        if user_indexes:
            idx = user_indexes[-1]
            messages[idx] = dict(messages[idx])
            messages[idx]["content"] = f"{messages[idx].get('content', '').rstrip()}\n\n{SCHEMA_PROMPT_INSTRUCTION}"
        else:
            messages.append({"role": "user", "content": SCHEMA_PROMPT_INSTRUCTION})
        if tokenizer is not None and hasattr(tokenizer, "apply_chat_template"):
            return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        return "\n\n".join(f"{msg.get('role', '').capitalize()}: {msg.get('content', '')}" for msg in messages) + "\n\nAssistant:"
    return f"{sample.prompt.rstrip()}\n\n{SCHEMA_PROMPT_INSTRUCTION}"


def _prompt_fingerprint(samples, tokenizer, prompt_style: str = "default") -> str:
    digest = hashlib.sha256()
    for sample in samples:
        digest.update(_render_prompt(sample, tokenizer=tokenizer, prompt_style=prompt_style).encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _replace_with_retrieved_context(samples: list[AnswerEvalSample], top_k: int) -> tuple[list[AnswerEvalSample], list[dict]]:
    pipeline = LegalQAPipeline.build(force_reindex=False)
    retrieved_samples: list[AnswerEvalSample] = []
    retrieval_metadata: list[dict] = []
    for sample in samples:
        similar = pipeline.artifacts.retriever.similar_questions(sample.question, top_k=5)
        heuristic = pipeline._heuristic_retrieval(sample.question, similar, top_k=max(top_k * 2, 50))
        reranked = pipeline.model_reranker.rerank(sample.question, heuristic, top_k=top_k)
        context = build_context(reranked, top_k=top_k)
        retrieved_samples.append(_sample_with_context(sample, context, reranked))
        retrieval_metadata.append(
            {
                "question": sample.question,
                "retrieval_variant": "full_with_cross_encoder_reranker",
                "retrieval_top_k": top_k,
                "reranker_mode": "cross-encoder" if pipeline.model_reranker.available() else "heuristic_fallback",
                "retrieved": [_compact_retrieved(item, rank) for rank, item in enumerate(reranked, start=1)],
            }
        )
    return retrieved_samples, retrieval_metadata


def _sample_with_context(sample: AnswerEvalSample, context: str, retrieved: list[dict]) -> AnswerEvalSample:
    messages = tuple(_replace_context_in_message(dict(message), context) for message in sample.messages)
    prompt = _replace_context_text(sample.prompt, context) if sample.prompt else sample.prompt
    metadata = {**(sample.metadata or {}), "evidence_mode": "retrieved_context", "retrieved": [_compact_retrieved(item, rank) for rank, item in enumerate(retrieved, start=1)]}
    return replace(sample, context=context, prompt=prompt, metadata=metadata, messages=messages)


def _replace_context_in_message(message: dict, context: str) -> dict:
    if message.get("role") != "user":
        return message
    message["content"] = _replace_context_text(str(message.get("content", "")), context)
    return message


def _replace_context_text(text: str, context: str) -> str:
    markers = (("Van ban phap ly:", "Cau hoi:"), ("Chung cu phap ly:", "Yeu cau tra loi:"))
    for start, end in markers:
        start_index = text.find(start)
        end_index = text.find(end, start_index + len(start)) if start_index >= 0 else -1
        if start_index >= 0 and end_index >= 0:
            return f"{text[:start_index + len(start)]}\n{context.strip()}\n\n{text[end_index:]}"
    return f"Van ban phap ly:\n{context.strip()}\n\n{text.strip()}"


def _compact_retrieved(item: dict, rank: int) -> dict:
    return {
        "rank": rank,
        "cid": item.get("cid"),
        "chunk_id": item.get("chunk_id"),
        "article": item.get("article"),
        "clause": item.get("clause"),
        "score": item.get("rerank_score", item.get("hybrid_score")),
        "sources": item.get("sources", []),
        "snippet": str(item.get("text", ""))[:500],
    }


def _attach_retrieval_metadata(metrics: dict, retrieval_metadata: list[dict]) -> None:
    by_question = {item.get("question"): item for item in retrieval_metadata}
    for detail in metrics.get("details", []):
        retrieval = by_question.get(detail.get("question"))
        if retrieval:
            detail["retrieval"] = retrieval


def _annotate_baseline_distinctness(rows: list[dict]) -> list[dict]:
    by_variant = {row.get("variant"): row for row in rows}
    prompt_only = by_variant.get("qwen_prompt_only")
    oracle = by_variant.get("oracle_evidence_qwen")
    if not prompt_only or not oracle:
        return rows

    metric_keys = (
        "exact_match",
        "token_f1",
        "rouge_l",
        "citation_presence",
        "format_compliance",
        "faithfulness_score",
        "reasoning_score",
        "directness_score",
        "citation_correctness",
        "refusal_quality",
    )
    same_input = bool(oracle.get("input_fingerprint")) and oracle.get("input_fingerprint") == prompt_only.get("input_fingerprint")
    same_metrics = all(oracle.get(key) == prompt_only.get(key) for key in metric_keys)
    if same_input or same_metrics:
        oracle["status"] = "not_distinct"
        oracle["exclude_from_main_table"] = True
        oracle["diagnostic_note"] = (
            "Current SFT evaluation prompt already contains oracle/gold context, so this row is not a distinct "
            "upper-bound baseline relative to qwen_prompt_only."
        )
    else:
        oracle["status"] = "distinct"
        oracle["exclude_from_main_table"] = False
    return rows


def _load_llm(args, variant: str, model_cache: dict):
    cache_key = "qwen_qlora" if variant == "qwen_qlora" else "base"
    if cache_key in model_cache:
        return model_cache[cache_key]
    try:
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("Missing inference dependencies. Install requirements-runpod.txt first.") from exc

    tokenizer = AutoTokenizer.from_pretrained(args.base_model, trust_remote_code=False)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        dtype=getattr(torch, "bfloat16", torch.float16),
        device_map="auto",
        trust_remote_code=False,
    )
    if variant == "qwen_qlora":
        adapter_path = Path(args.adapter)
        if not adapter_path.exists():
            raise SystemExit(f"Adapter path not found: {adapter_path}")
        model = PeftModel.from_pretrained(model, str(adapter_path))
    model.eval()
    model_cache[cache_key] = (tokenizer, model)
    return tokenizer, model


def _sample_context_as_evidence(sample) -> list[dict]:
    text = sample.context.strip()
    if not text:
        return []
    metadata = sample.metadata or {}
    return [
        {
            "chunk_id": str(metadata.get("chunk_id") or metadata.get("id") or "oracle-context"),
            "cid": str(metadata.get("cid") or metadata.get("id") or "oracle-context"),
            "title": metadata.get("doc_name") or metadata.get("title") or "Oracle evidence",
            "doc_name": metadata.get("doc_name") or metadata.get("title") or "Oracle evidence",
            "doc_number": metadata.get("doc_number"),
            "article": metadata.get("article") or metadata.get("article_number"),
            "clause": metadata.get("clause"),
            "text": text,
            "hybrid_score": 10.0,
            "rerank_score": 10.0,
            "sources": ["oracle_context"],
        }
    ]


def _render_markdown(metrics: dict) -> str:
    lines = [
        "# Answer Generation Report",
        "",
        f"- Variant: {metrics.get('variant', 'qwen_qlora')}",
        f"- Evidence Mode: {metrics.get('evidence_mode', '')}",
        f"- Retrieval Variant: {metrics.get('retrieval_variant', '')}",
        f"- Retrieval Top-k: {metrics.get('retrieval_top_k', '')}",
        f"- Prompt Style: {metrics.get('prompt_style', 'default')}",
        f"- Samples: {metrics.get('samples', 0)}",
        f"- Exact Match: {metrics.get('exact_match', 0.0)}",
        f"- Token F1: {metrics.get('token_f1', 0.0)}",
        f"- ROUGE-L: {metrics.get('rouge_l', 0.0)}",
        f"- Citation Presence: {metrics.get('citation_presence', 0.0)}",
        f"- Format Compliance: {metrics.get('format_compliance', metrics.get('structure_score', 0.0))}",
        f"- Faithfulness Score: {metrics.get('faithfulness_score', 0.0)}",
        f"- Reasoning Score: {metrics.get('reasoning_score', 0.0)}",
        f"- Directness Score: {metrics.get('directness_score', 0.0)}",
        f"- Citation Correctness: {metrics.get('citation_correctness', 0.0)}",
        f"- Refusal Quality: {metrics.get('refusal_quality', 0.0)}",
        f"- Avg Prediction Length: {metrics.get('avg_prediction_length', 0.0)}",
        f"- Avg Gold Length: {metrics.get('avg_gold_length', 0.0)}",
    ]
    return "\n".join(lines)


def _render_baselines_markdown(payload: dict) -> str:
    columns = [
        "variant",
        "status",
        "samples",
        "exact_match",
        "token_f1",
        "rouge_l",
        "citation_presence",
        "format_compliance",
        "faithfulness_score",
        "reasoning_score",
        "directness_score",
        "citation_correctness",
        "refusal_quality",
        "avg_prediction_length",
    ]
    lines = ["# Generation Baselines Report", "", "| " + " | ".join(columns) + " |", "|" + "|".join("---" for _ in columns) + "|"]
    for row in payload.get("baselines", []):
        lines.append("| " + " | ".join(str(row.get(column, "")) for column in columns) + " |")
    diagnostics = [
        row
        for row in payload.get("baselines", [])
        if row.get("status") == "not_distinct" or row.get("diagnostic_note")
    ]
    if diagnostics:
        lines.extend(["", "## Diagnostics", ""])
        for row in diagnostics:
            lines.append(f"- `{row.get('variant')}`: {row.get('diagnostic_note') or row.get('status')}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
