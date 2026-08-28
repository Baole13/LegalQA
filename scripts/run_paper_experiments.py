from __future__ import annotations

import argparse
import csv
import io
import json
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from statistics import mean, pstdev
from typing import Iterable

import scripts._bootstrap as _bootstrap

from src.data.load_qa import load_qa_records, parse_cids
from src.evaluation.retrieval_eval import ndcg_at_k
from src.qa.pipeline import LegalQAPipeline
from src.retrieval.bm25_okapi_retriever import BM25OkapiRetriever
from src.utils.io import load_json, save_json, save_jsonl

HUMAN_METRICS = ("legal_correctness", "grounding", "citation_correctness", "directness", "refusal")
END_TO_END_HUMAN_METRICS = HUMAN_METRICS + ("citation_support_score",)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run paper experiments and render Markdown tables for the LegalQA study."
    )
    parser.add_argument("--retrieval-dataset", default="data/raw/yuitc/test.parquet")
    parser.add_argument("--answer-report", default="reports/answer_generation_report.json")
    parser.add_argument("--generation-baselines-report", default="reports/generation_baselines_report.json")
    parser.add_argument("--retrieved-generation-report", default="reports/answer_generation_qwen_qlora_retrieved_report.json")
    parser.add_argument("--retrieved-prompt-only-report", default="reports/answer_generation_qwen_prompt_only_retrieved_report.json")
    parser.add_argument("--retrieved-schema-report", default="reports/answer_generation_qwen_qlora_retrieved_schema_report.json")
    parser.add_argument("--qa-memory-leakage-report", default="reports/qa_memory_leakage_audit.json")
    parser.add_argument("--report-dir", default="reports")
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--top-k-ablation", type=int, nargs="+", default=[3, 5, 8])
    parser.add_argument("--human-eval", default=None, help="Optional completed human evaluation CSV.")
    parser.add_argument("--human-sample-size", type=int, default=75)
    parser.add_argument("--end-to-end-human-eval", default=None, help="Optional completed end-to-end human evaluation TSV/CSV.")
    parser.add_argument("--end-to-end-human-sample-size", type=int, default=50)
    args = parser.parse_args()

    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    pipeline = LegalQAPipeline.build()
    dataset_stats = _dataset_stats()
    max_eval_k = max(args.top_k, max(args.top_k_ablation), 20)
    metric_ks = (1, 5, 10, 20)
    pipeline.artifacts.retriever.neural_dense.ensure_available()
    retrieval_cache_dir = report_dir / ".paper_experiment_cache"
    retrieval, retrieval_details = _evaluate_retrieval_variant(
        pipeline=pipeline,
        variant="full",
        qa_path=args.retrieval_dataset,
        limit=args.limit,
        top_k=max_eval_k,
        ks=metric_ks,
        cache_dir=retrieval_cache_dir,
    )
    ablations = _run_retrieval_ablations(
        pipeline=pipeline,
        qa_path=args.retrieval_dataset,
        limit=args.limit,
        top_ks=args.top_k_ablation,
        full_metrics=retrieval,
        full_details=retrieval_details,
        cache_dir=retrieval_cache_dir,
    )
    main_retrieval_row = _select_main_retrieval_result(ablations, fallback=retrieval)
    if main_retrieval_row.get("variant") == "full_with_cross_encoder_reranker":
        retrieval, retrieval_details = _evaluate_retrieval_variant(
            pipeline=pipeline,
            variant="full_with_cross_encoder_reranker",
            qa_path=args.retrieval_dataset,
            limit=args.limit,
            top_k=max_eval_k,
            ks=metric_ks,
            cache_dir=retrieval_cache_dir,
        )
        retrieval["reranker_mode"] = main_retrieval_row.get("reranker_mode", "cross-encoder")
        retrieval["reranker_model_path"] = main_retrieval_row.get("reranker_model_path")
        retrieval["main_result_note"] = "Main retrieval result uses the trained cross-encoder reranker; heuristic retrieval is retained as an ablation."
    else:
        retrieval = main_retrieval_row
    answer_report = _load_answer_report(args.answer_report)
    retrieved_generation = _load_answer_report(args.retrieved_generation_report)
    retrieved_prompt_only_generation = _load_answer_report(args.retrieved_prompt_only_report)
    retrieved_schema_generation = _load_answer_report(args.retrieved_schema_report)
    qa_memory_leakage = _load_json_if_exists(args.qa_memory_leakage_report)
    generation_baselines = _load_generation_baselines(args.generation_baselines_report)
    retrieval_details = _attach_answer_details(retrieval_details, answer_report.get("details", []))
    retrieval_error_categories = _categorize_retrieval_errors(retrieval_details)
    generation_error_categories = _categorize_generation_errors(answer_report.get("details", []))
    human_eval_sample = _build_human_eval_sample(
        answer_details=answer_report.get("details", []),
        retrieval_details=retrieval_details,
        sample_size=args.human_sample_size,
    )
    human_eval_summary = _load_or_initialize_human_eval(args.human_eval, human_eval_sample)
    human_eval_rows = _read_delimited_rows(Path(args.human_eval)) if args.human_eval and Path(args.human_eval).exists() else []
    human_error_categories = _categorize_human_errors(human_eval_rows)
    end_to_end_human_eval_sample = _build_end_to_end_human_eval_sample(
        retrieved_generation.get("details", []),
        sample_size=args.end_to_end_human_sample_size,
    )
    end_to_end_human_eval_summary = _load_or_initialize_end_to_end_human_eval(
        args.end_to_end_human_eval,
        end_to_end_human_eval_sample,
    )
    case_studies = _select_case_studies(answer_report.get("details", []), retrieval_details)

    notes = [
        "Faithfulness, reasoning, directness, citation correctness, and refusal quality are proxy metrics.",
        "Human evaluation uses two human annotators who scored independently after a short 3-5 example calibration; no AI-assisted scoring is reported as human evaluation.",
        "The hybrid_no_qa_memory ablation disables QA-memory seeding/boosting during retrieval evaluation only.",
        "Top-k ablation rows cap the number of retrieved evidence chunks available to downstream generation.",
        "The main retrieval table uses the trained cross-encoder reranker when the full_with_cross_encoder_reranker row is available; heuristic full retrieval is reported as an ablation.",
        "Format compliance measures adherence to the expected structured output format, not legal correctness; low values are treated as a formatting limitation.",
    ]
    oracle_rows = [
        row
        for row in generation_baselines.get("baselines", [])
        if row.get("variant") == "oracle_evidence_qwen" and row.get("status") == "not_distinct"
    ]
    if oracle_rows:
        notes.append(
            "oracle_evidence_qwen is diagnostic only: the current SFT prompt already contains oracle/gold context, so it is not a distinct upper-bound baseline."
        )
    answer_samples = int(answer_report.get("samples", 0) or 0)
    if answer_samples and answer_samples != args.limit:
        notes.append(
            f"Answer generation report contains {answer_samples} samples, not the {args.limit}-sample retrieval run; do not claim it as the main {args.limit}-sample generation result."
        )
    retrieved_samples = int(retrieved_generation.get("samples", 0) or 0)
    if retrieved_samples and retrieved_samples < 200:
        notes.append(
            f"Retrieved-context generation report contains only {retrieved_samples} samples; treat it as a smoke validation, not a paper-scale end-to-end RAG generation result."
        )
    if not retrieved_prompt_only_generation:
        notes.append("Retrieved-context prompt-only baseline is missing; do not compare base Qwen vs QLoRA end-to-end until it is generated.")
    if not retrieved_schema_generation:
        notes.append("Schema prompting report is missing; format-compliance before/after remains pending.")
    elif int(retrieved_schema_generation.get("samples", 0) or 0) < 200:
        notes.append(
            f"Schema prompting report contains only {int(retrieved_schema_generation.get('samples', 0) or 0)} samples; treat it as smoke validation and do not claim schema prompting improves format compliance."
        )

    payload = {
        "dataset_stats": dataset_stats,
        "retrieval": retrieval,
        "retrieval_ablations": ablations,
        "answer_generation": {key: value for key, value in answer_report.items() if key != "details"},
        "retrieved_answer_generation": {key: value for key, value in retrieved_generation.items() if key != "details"},
        "retrieved_prompt_only_generation": {key: value for key, value in retrieved_prompt_only_generation.items() if key != "details"},
        "retrieved_schema_generation": {key: value for key, value in retrieved_schema_generation.items() if key != "details"},
        "generation_baselines": generation_baselines,
        "qa_memory_leakage": qa_memory_leakage,
        "human_evaluation": human_eval_summary,
        "end_to_end_human_evaluation": end_to_end_human_eval_summary,
        "retrieval_error_categories": retrieval_error_categories,
        "generation_error_categories": generation_error_categories,
        "human_error_categories": human_error_categories,
        "answer_error_categories": _merge_error_categories(retrieval_error_categories, generation_error_categories),
        "case_studies": case_studies,
        "notes": notes,
    }

    json_path = report_dir / "paper_experiments.json"
    md_path = report_dir / "paper_experiments.md"
    details_path = report_dir / "paper_retrieval_details.jsonl"
    human_jsonl_path = report_dir / f"human_eval_sample_{args.human_sample_size}.jsonl"
    human_csv_path = report_dir / f"human_eval_sample_{args.human_sample_size}.csv"
    e2e_human_jsonl_path = report_dir / f"end_to_end_human_eval_sample_{args.end_to_end_human_sample_size}.jsonl"
    e2e_human_tsv_path = report_dir / f"end_to_end_human_eval_sample_{args.end_to_end_human_sample_size}.tsv"

    save_json(json_path, payload)
    save_jsonl(details_path, retrieval_details)
    human_jsonl_written = _write_human_eval_jsonl(human_jsonl_path, human_eval_sample)
    human_csv_written = _write_human_eval_csv(human_csv_path, human_eval_sample)
    e2e_human_jsonl_written = _write_human_eval_jsonl(e2e_human_jsonl_path, end_to_end_human_eval_sample)
    e2e_human_tsv_written = _write_tsv(e2e_human_tsv_path, end_to_end_human_eval_sample, metrics=END_TO_END_HUMAN_METRICS)
    _write_human_eval_summary(report_dir, human_eval_summary)
    _write_end_to_end_human_eval_summary(report_dir, end_to_end_human_eval_summary)
    md_path.write_text(_render_markdown(payload), encoding="utf-8")

    print(json.dumps({key: value for key, value in payload.items() if key != "notes"}, ensure_ascii=False, indent=2))
    print(f"Saved: {json_path}")
    print(f"Saved: {md_path}")
    print(f"Saved: {details_path}")
    print(f"{'Saved' if human_jsonl_written else 'Preserved annotated file'}: {human_jsonl_path}")
    print(f"{'Saved' if human_csv_written else 'Preserved annotated file'}: {human_csv_path}")
    print(f"{'Saved' if e2e_human_jsonl_written else 'Preserved annotated file'}: {e2e_human_jsonl_path}")
    print(f"{'Saved' if e2e_human_tsv_written else 'Preserved annotated file'}: {e2e_human_tsv_path}")


def _load_json_if_exists(path: str | Path) -> dict:
    active = Path(path)
    if not active.exists():
        return {}
    return json.loads(active.read_text(encoding="utf-8"))


def _dataset_stats() -> dict:
    stats: dict[str, object] = {}
    index_manifest = Path("data/indexes/manifest_v3.json")
    sft_manifest = Path("data/processed/thangvip_legalqa/manifest.json")
    retrieval_manifest = Path("data/aligned/retrieval_manifest.json")
    qlora_manifest = Path("models/qwen2.5-7b-legalqa-qlora/training_manifest.json")
    if index_manifest.exists():
        manifest = load_json(index_manifest)
        stats["corpus_chunks"] = manifest.get("corpus_chunks")
        stats["qa_memory_records"] = manifest.get("qa_memory_records")
        stats["index_created_at"] = manifest.get("created_at")
    if sft_manifest.exists():
        manifest = load_json(sft_manifest)
        stats["sft_total_records"] = manifest.get("total_records")
        stats["sft_train_records"] = manifest.get("train_records")
        stats["sft_val_records"] = manifest.get("val_records")
        stats["sft_test_records"] = manifest.get("test_records")
    if retrieval_manifest.exists():
        manifest = load_json(retrieval_manifest)
        stats["retriever_records"] = manifest.get("retriever_records")
        stats["reranker_records"] = manifest.get("reranker_records")
        stats["negatives_per_query"] = manifest.get("negatives_per_query")
    if qlora_manifest.exists():
        manifest = load_json(qlora_manifest)
        stats["base_model"] = manifest.get("base_model")
        stats["qlora_train_records"] = manifest.get("train_records")
        stats["qlora_eval_records"] = manifest.get("eval_records")
    return stats


def _select_main_retrieval_result(ablations: list[dict], fallback: dict) -> dict:
    for row in ablations:
        if row.get("variant") == "full_with_cross_encoder_reranker":
            return dict(row)
    return dict(fallback)


def _run_retrieval_ablations(
    pipeline: LegalQAPipeline,
    qa_path: str,
    limit: int,
    top_ks: Iterable[int],
    full_metrics: dict | None = None,
    full_details: list[dict] | None = None,
    cache_dir: Path | None = None,
) -> list[dict]:
    pipeline.artifacts.retriever.neural_dense.ensure_available()
    rows: list[dict] = []
    metric_ks = (1, 5, 10, 20)
    if full_metrics is None or full_details is None:
        full_metrics, full_details = _evaluate_retrieval_variant(pipeline, "full", qa_path, limit, max(metric_ks), metric_ks, cache_dir=cache_dir)
    bm25_only, _ = _evaluate_retrieval_variant(pipeline, "bm25_only", qa_path, limit, max(metric_ks), metric_ks, cache_dir=cache_dir)
    bm25_okapi_only, _ = _evaluate_retrieval_variant(pipeline, "bm25_okapi_only", qa_path, limit, max(metric_ks), metric_ks, cache_dir=cache_dir)
    dense_only, _ = _evaluate_retrieval_variant(pipeline, "dense_only", qa_path, limit, max(metric_ks), metric_ks, cache_dir=cache_dir)
    with _qa_memory_disabled(pipeline):
        hybrid_no_qa, _ = _evaluate_retrieval_variant(
            pipeline,
            "hybrid_no_qa_memory",
            qa_path,
            limit,
            max(metric_ks),
            metric_ks,
            cache_dir=cache_dir,
        )
    hybrid_with_qa, _ = _evaluate_retrieval_variant(
        pipeline,
        "hybrid_with_qa_memory",
        qa_path,
        limit,
        max(metric_ks),
        metric_ks,
        cache_dir=cache_dir,
    )

    without_model = {**full_metrics, "variant": "full_without_model_reranker", "reranker_mode": "heuristic"}
    with_model, _ = _evaluate_retrieval_variant(
        pipeline,
        "full_with_cross_encoder_reranker",
        qa_path,
        limit,
        max(metric_ks),
        metric_ks,
        cache_dir=cache_dir,
    )
    with_model["reranker_mode"] = "cross-encoder" if pipeline.model_reranker.available() else "heuristic_fallback"
    with_model["reranker_model_path"] = pipeline.serving_config.reranker_model_path
    with_model_k100, _ = _evaluate_retrieval_variant(
        pipeline,
        "full_with_cross_encoder_reranker_k100",
        qa_path,
        limit,
        max(metric_ks),
        metric_ks,
        cache_dir=cache_dir,
    )
    rows.extend(
        [
            bm25_only,
            bm25_okapi_only,
            dense_only,
            hybrid_no_qa,
            hybrid_with_qa,
            without_model,
            with_model,
            with_model_k100,
            full_metrics,
        ]
    )
    for top_k in top_ks:
        rows.append(_metrics_from_details(full_details, f"full_top_k_{top_k}", qa_path, full_metrics, top_k, metric_ks))
    return rows


@contextmanager
def _qa_memory_disabled(pipeline: LegalQAPipeline):
    retriever = pipeline.artifacts.retriever
    original_search_similar = retriever._search_similar_questions
    original_weights = dict(retriever.weights)
    original_qa_config = dict(retriever.qa_config)
    retriever._search_similar_questions = lambda query, top_k=5: []
    retriever.weights = {**retriever.weights, "qa_boost": 0.0}
    retriever.qa_config = {**retriever.qa_config, "top_k": 0, "seed_top_hits": 0}
    try:
        yield
    finally:
        retriever._search_similar_questions = original_search_similar
        retriever.weights = original_weights
        retriever.qa_config = original_qa_config


@contextmanager
def _hybrid_weights(pipeline: LegalQAPipeline, **weights: float):
    retriever = pipeline.artifacts.retriever
    original_weights = dict(retriever.weights)
    retriever.weights = {**retriever.weights, **weights}
    try:
        yield
    finally:
        retriever.weights = original_weights


def _evaluate_retrieval_variant(
    pipeline: LegalQAPipeline,
    variant: str,
    qa_path: str,
    limit: int,
    top_k: int,
    ks: tuple[int, ...],
    cache_dir: Path | None = None,
) -> tuple[dict, list[dict]]:
    records = load_qa_records(qa_path)[:limit]
    cached_details = _load_cached_variant_details(cache_dir, variant, limit, top_k)
    if cached_details is not None:
        cached_details = _ensure_gold_evidence(cached_details, pipeline)
        return _metrics_from_details(cached_details, variant, qa_path, _metrics_template(pipeline), top_k, ks), cached_details
    cache_path = _variant_cache_path(cache_dir, variant, limit, top_k)
    if cache_path is not None and cache_path.exists():
        cache_path.unlink()
    hit_counts = {k: 0 for k in ks}
    covered_hit_counts = {k: 0 for k in ks}
    reciprocal_rank_sum = 0.0
    covered_reciprocal_rank_sum = 0.0
    covered_questions = 0
    questions_without_gold_in_index = 0
    ndcg_sum = 0.0
    details: list[dict] = []
    indexed_cids = {str(item["cid"]) for item in pipeline.artifacts.store.corpus_meta}

    for index, record in enumerate(records):
        gold_cids = set(parse_cids(record.get("cid", "")))
        if not gold_cids:
            continue

        gold_in_index = any(cid in indexed_cids for cid in gold_cids)
        gold_evidence = [
            _compact_gold_item(item)
            for item in pipeline.artifacts.store.fetch_chunks_by_cids(sorted(gold_cids), limit_per_cid=1)
        ]
        covered_questions += int(gold_in_index)
        questions_without_gold_in_index += int(not gold_in_index)

        results = _search_variant(pipeline, variant, record["question"], top_k=top_k)
        ranked_cids = [str(item["cid"]) for item in results]
        ndcg_sum += ndcg_at_k(ranked_cids, gold_cids, 10)
        for k in ks:
            hit = any(cid in gold_cids for cid in ranked_cids[:k])
            hit_counts[k] += int(hit)
            covered_hit_counts[k] += int(gold_in_index and hit)

        hit_rank = None
        for rank, cid in enumerate(ranked_cids, start=1):
            if cid in gold_cids:
                hit_rank = rank
                reciprocal_rank_sum += 1.0 / rank
                if gold_in_index:
                    covered_reciprocal_rank_sum += 1.0 / rank
                break

        detail = {
            "id": f"{variant}-{index:04d}",
            "variant": variant,
            "sample_index": index,
            "question": record.get("question", ""),
            "gold_cids": sorted(gold_cids),
            "gold_evidence": gold_evidence,
            "gold_in_index": gold_in_index,
            "hit_rank": hit_rank,
            "error_labels": _retrieval_error_labels(gold_in_index, hit_rank),
            "retrieved": [_compact_retrieved_item(item, rank) for rank, item in enumerate(results, start=1)],
        }
        details.append(detail)
        _append_variant_cache(cache_path, detail)

    total = max(len(records), 1)
    covered_total = max(covered_questions, 1)
    metrics = {
        "variant": variant,
        "qa_path": str(Path(qa_path)),
        "samples": len(records),
        "top_k": top_k,
        "indexed_chunks": len(pipeline.artifacts.store.corpus_meta),
        "indexed_unique_cids": len(indexed_cids),
        "gold_coverage_in_index": round(covered_questions / total, 4),
        "questions_with_gold_in_index": covered_questions,
        "questions_without_gold_in_index": questions_without_gold_in_index,
        "mrr": round(reciprocal_rank_sum / total, 4),
        "conditional_mrr": round(covered_reciprocal_rank_sum / covered_total, 4),
    }
    for k in ks:
        metrics[f"recall@{k}"] = round(hit_counts[k] / total, 4)
        metrics[f"conditional_recall@{k}"] = round(covered_hit_counts[k] / covered_total, 4)
    return metrics, details


def _metrics_template(pipeline: LegalQAPipeline) -> dict:
    indexed_cids = {str(item["cid"]) for item in pipeline.artifacts.store.corpus_meta}
    return {
        "indexed_chunks": len(pipeline.artifacts.store.corpus_meta),
        "indexed_unique_cids": len(indexed_cids),
    }


def _variant_cache_path(cache_dir: Path | None, variant: str, limit: int, top_k: int) -> Path | None:
    if cache_dir is None:
        return None
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"retrieval_v2_{variant}_limit{limit}_top{top_k}.jsonl"


def _load_cached_variant_details(cache_dir: Path | None, variant: str, limit: int, top_k: int) -> list[dict] | None:
    path = _variant_cache_path(cache_dir, variant, limit, top_k)
    if path is None or not path.exists():
        return None
    details = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    details.append(json.loads(line))
    except (OSError, json.JSONDecodeError):
        return None
    if len(details) >= limit:
        return details[:limit]
    return None


def _ensure_gold_evidence(details: list[dict], pipeline: LegalQAPipeline) -> list[dict]:
    for detail in details:
        if detail.get("gold_evidence"):
            continue
        gold_cids = [str(cid) for cid in detail.get("gold_cids", [])]
        detail["gold_evidence"] = [
            _compact_gold_item(item)
            for item in pipeline.artifacts.store.fetch_chunks_by_cids(gold_cids, limit_per_cid=1)
        ]
    return details


def _append_variant_cache(path: Path | None, detail: dict) -> None:
    if path is None:
        return
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(detail, ensure_ascii=False) + "\n")


def _retrieval_error_labels(gold_in_index: bool, hit_rank: int | None) -> list[str]:
    labels = []
    if not gold_in_index:
        labels.append("missing_gold_in_index")
    if hit_rank is None:
        labels.append("retrieval_miss")
    return labels


def _attach_answer_details(retrieval_details: list[dict], answer_details: list[dict]) -> list[dict]:
    answer_by_question = {item.get("question"): item for item in answer_details}
    merged = []
    for item in retrieval_details:
        answer = answer_by_question.get(item.get("question"), {})
        prediction_text = str(answer.get("prediction_text", answer.get("prediction", ""))).strip()
        labels = list(item.get("error_labels") or [])
        labels.extend(_answer_error_labels(answer))
        merged.append(
            {
                **item,
                "gold_answer": answer.get("gold_answer", ""),
                "prediction": prediction_text,
                "answer_metrics": {
                    key: answer.get(key)
                    for key in (
                        "token_f1",
                        "rouge_l",
                        "citation_presence",
                        "faithfulness_score",
                        "directness_score",
                        "citation_correctness",
                        "refusal_quality",
                    )
                    if key in answer
                },
                "error_labels": sorted(set(labels)),
            }
        )
    return merged


def _answer_error_labels(answer: dict) -> list[str]:
    if not answer:
        return []
    labels = []
    prediction_text = str(answer.get("prediction_text", answer.get("prediction", ""))).strip()
    gold_length = float(answer.get("gold_length", 0.0) or 0.0)
    prediction_length = float(answer.get("prediction_length", len(prediction_text)) or 0.0)
    if float(answer.get("faithfulness_score", 0.0)) < 0.35:
        labels.append("low_grounding_proxy")
    if float(answer.get("citation_presence", 0.0)) < 1.0 or float(answer.get("citation_correctness", 1.0)) < 0.5:
        labels.append("wrong_or_weak_citation_proxy")
    if float(answer.get("directness_score", 1.0)) < 0.5:
        labels.append("indirect_answer_proxy")
    if gold_length > 0 and prediction_length > gold_length * 1.25:
        labels.append("verbose_answer_candidate")
    if _is_refusal(prediction_text):
        labels.append("over_refusal_candidate")
    if not _is_refusal(prediction_text) and float(answer.get("faithfulness_score", 1.0)) < 0.2:
        labels.append("under_refusal_candidate")
    return labels


def _metrics_from_details(
    details: list[dict],
    variant: str,
    qa_path: str,
    template: dict,
    top_k: int,
    ks: tuple[int, ...],
) -> dict:
    total = max(len(details), 1)
    covered_questions = sum(1 for item in details if item.get("gold_in_index"))
    covered_total = max(covered_questions, 1)
    hit_counts = {k: 0 for k in ks}
    covered_hit_counts = {k: 0 for k in ks}
    reciprocal_rank_sum = 0.0
    covered_reciprocal_rank_sum = 0.0
    ndcg_sum = 0.0

    for item in details:
        gold_cids = set(str(cid) for cid in item.get("gold_cids", []))
        capped = (item.get("retrieved") or [])[:top_k]
        ranked_cids = [str(hit.get("cid", "")) for hit in capped]
        ndcg_sum += ndcg_at_k(ranked_cids, gold_cids, 10)
        for k in ks:
            hit = any(cid in gold_cids for cid in ranked_cids[:k])
            hit_counts[k] += int(hit)
            covered_hit_counts[k] += int(item.get("gold_in_index") and hit)
        for rank, cid in enumerate(ranked_cids, start=1):
            if cid in gold_cids:
                reciprocal_rank_sum += 1.0 / rank
                if item.get("gold_in_index"):
                    covered_reciprocal_rank_sum += 1.0 / rank
                break

    metrics = {
        "variant": variant,
        "qa_path": str(Path(qa_path)),
        "samples": len(details),
        "top_k": top_k,
        "indexed_chunks": template.get("indexed_chunks"),
        "indexed_unique_cids": template.get("indexed_unique_cids"),
        "gold_coverage_in_index": round(covered_questions / total, 4),
        "questions_with_gold_in_index": covered_questions,
        "questions_without_gold_in_index": len(details) - covered_questions,
        "mrr": round(reciprocal_rank_sum / total, 4),
        "conditional_mrr": round(covered_reciprocal_rank_sum / covered_total, 4),
        "ndcg@10": round(ndcg_sum / total, 4),
    }
    for k in ks:
        metrics[f"recall@{k}"] = round(hit_counts[k] / total, 4)
        metrics[f"conditional_recall@{k}"] = round(covered_hit_counts[k] / covered_total, 4)
    return metrics


def _search_variant(pipeline: LegalQAPipeline, variant: str, question: str, top_k: int) -> list[dict]:
    if variant == "bm25_only":
        return _bm25_only_search(pipeline, question, top_k=top_k)
    if variant == "bm25_okapi_only":
        return _bm25_okapi_only_search(pipeline, question, top_k=top_k)
    if variant == "dense_only":
        return _dense_only_search(pipeline, question, top_k=top_k)
    if variant == "hybrid_no_qa_memory":
        return pipeline._heuristic_retrieval(question, [], top_k=top_k)
    # hybrid_with_qa_memory and full both use hybrid retrieval plus QA-memory.
    similar_questions = pipeline.artifacts.retriever.similar_questions(question, top_k=5)
    if variant in _CROSS_ENCODER_DEPTHS:
        depth = _CROSS_ENCODER_DEPTHS[variant]
        heuristic = pipeline._heuristic_retrieval(question, similar_questions, top_k=max(top_k * 2, depth))
        return pipeline.model_reranker.rerank(question, heuristic, top_k=top_k)
    return pipeline._heuristic_retrieval(question, similar_questions, top_k=top_k)


_CROSS_ENCODER_DEPTHS = {
    "full_with_cross_encoder_reranker": 50,
    "full_with_cross_encoder_reranker_k100": 100,
    "full_with_cross_encoder_reranker_k200": 200,
}


def _bm25_okapi_only_search(pipeline: LegalQAPipeline, question: str, top_k: int) -> list[dict]:
    candidates = _okapi_retriever(pipeline).search(question, top_k=max(top_k * 24, 120))
    hydrated = [
        {
            **item,
            "dense_score": 0.0,
            "qa_boost": 0.0,
            "hybrid_score": float(item.get("bm25_score", 0.0)),
            "sources": ["bm25-okapi"],
        }
        for item in candidates
    ]
    return pipeline.heuristic_reranker.rerank(question, hydrated, top_k=top_k)


def _okapi_retriever(pipeline: LegalQAPipeline) -> "BM25OkapiRetriever":
    cached = getattr(pipeline, "_okapi_retriever", None)
    if cached is None:
        cached = BM25OkapiRetriever(pipeline.artifacts.store)
        pipeline._okapi_retriever = cached
    return cached


def _dense_only_search(pipeline: LegalQAPipeline, question: str, top_k: int) -> list[dict]:
    dense = pipeline.artifacts.retriever.neural_dense
    candidates = dense.search(question, top_k=max(top_k * 24, 120))
    hydrated = [
        {
            **item,
            "qa_boost": 0.0,
            "hybrid_score": float(item.get("neural_dense_score", 0.0)),
            "sources": ["neural-dense"],
        }
        for item in candidates
    ]
    return pipeline.heuristic_reranker.rerank(question, hydrated, top_k=top_k)


def _bm25_only_search(pipeline: LegalQAPipeline, question: str, top_k: int) -> list[dict]:
    candidates = pipeline.artifacts.retriever.bm25.search(question, top_k=max(top_k * 24, 120))
    row_ids = [int(item["row_id"]) for item in candidates if "row_id" in item]
    texts = pipeline.artifacts.store.fetch_chunk_texts(row_ids)
    hydrated = []
    for item in candidates:
        hydrated.append(
            {
                **item,
                "text": texts.get(int(item.get("row_id", -1)), item.get("text", "")),
                "dense_score": 0.0,
                "qa_boost": 0.0,
                "hybrid_score": float(item.get("bm25_score", 0.0)),
                "sources": ["bm25"],
            }
        )
    return pipeline.heuristic_reranker.rerank(question, hydrated, top_k=top_k)


def _compact_retrieved_item(item: dict, rank: int) -> dict:
    text = str(item.get("text", "")).replace("\n", " ").strip()
    return {
        "rank": rank,
        "cid": str(item.get("cid", "")),
        "chunk_id": item.get("chunk_id"),
        "title": item.get("title"),
        "article": item.get("article"),
        "clause": item.get("clause"),
        "sources": item.get("sources") or [],
        "score": item.get("rerank_score", item.get("hybrid_score")),
        "snippet": text[:600],
    }


def _compact_gold_item(item: dict) -> dict:
    text = str(item.get("text", "")).replace("\n", " " ).strip()
    return {
        "cid": str(item.get("cid", "")),
        "chunk_id": item.get("chunk_id"),
        "title": item.get("title"),
        "article": item.get("article"),
        "clause": item.get("clause"),
        "snippet": text[:600],
    }



def _load_generation_baselines(path: str) -> dict:
    report_path = Path(path)
    if not report_path.exists():
        return {"status": "missing", "baselines": []}
    payload = load_json(report_path)
    baselines = [_normalize_generation_metrics(row) for row in (payload.get("baselines") or [])]
    baselines = _annotate_generation_baseline_rows(baselines)
    return {"status": "available", **payload, "baselines": baselines}


def _annotate_generation_baseline_rows(rows: list[dict]) -> list[dict]:
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
    elif oracle.get("status") is None:
        oracle["status"] = "distinct"
    return rows

def _load_answer_report(path: str) -> dict:
    report_path = Path(path)
    if not report_path.exists():
        return {"samples": 0, "details": []}
    return _normalize_generation_metrics(load_json(report_path))


def _normalize_generation_metrics(payload: dict) -> dict:
    normalized = dict(payload)
    if "format_compliance" not in normalized and "structure_score" in normalized:
        normalized["format_compliance"] = normalized.get("structure_score")
    normalized.pop("structure_score", None)
    details = []
    for item in normalized.get("details", []) or []:
        detail = dict(item)
        if "format_compliance" not in detail and "structure_score" in detail:
            detail["format_compliance"] = detail.get("structure_score")
        detail.pop("structure_score", None)
        details.append(detail)
    if "details" in normalized:
        normalized["details"] = details
    return normalized


def _categorize_retrieval_errors(retrieval_details: list[dict]) -> dict:
    counter: Counter[str] = Counter()
    examples: dict[str, dict] = {}
    for item in retrieval_details:
        if not item.get("gold_in_index"):
            _add_error(counter, examples, "missing_gold_in_index", item)
        if item.get("hit_rank") is None:
            _add_error(counter, examples, "retrieval_miss", item)
        elif int(item.get("hit_rank") or 0) > 5:
            _add_error(counter, examples, "low_rank_after_top5", item)
    return _error_payload(counter, examples, denominator=len(retrieval_details), denominator_label="retrieval_samples")


def _categorize_generation_errors(answer_details: list[dict]) -> dict:
    counter: Counter[str] = Counter()
    examples: dict[str, dict] = {}
    for item in answer_details:
        prediction_text = str(item.get("prediction_text", item.get("prediction", ""))).strip()
        gold_length = float(item.get("gold_length", 0.0) or 0.0)
        prediction_length = float(item.get("prediction_length", len(prediction_text)) or 0.0)
        if float(item.get("faithfulness_score", 0.0)) < 0.35:
            _add_error(counter, examples, "low_grounding_proxy", item)
        if float(item.get("token_f1", 0.0)) < 0.35 and float(item.get("rouge_l", 0.0)) < 0.3:
            _add_error(counter, examples, "weak_lexical_match", item)
        if float(item.get("citation_presence", 0.0)) < 1.0 or float(item.get("citation_correctness", 1.0)) < 0.5:
            _add_error(counter, examples, "wrong_or_weak_citation_proxy", item)
        if float(item.get("format_compliance", item.get("structure_score", 1.0)) or 0.0) < 0.5:
            _add_error(counter, examples, "low_format_compliance", item)
        if _is_refusal(prediction_text):
            _add_error(counter, examples, "over_refusal_candidate", item)
        if not _is_refusal(prediction_text) and float(item.get("faithfulness_score", 1.0)) < 0.2:
            _add_error(counter, examples, "under_refusal_candidate", item)
        if gold_length > 0 and prediction_length > gold_length * 1.25:
            _add_error(counter, examples, "verbose_answer_candidate", item)
        if float(item.get("directness_score", 1.0)) < 0.5:
            _add_error(counter, examples, "indirect_answer_proxy", item)
    return _error_payload(counter, examples, denominator=len(answer_details), denominator_label="generation_samples")


def _categorize_human_errors(rows: list[dict], metric_names: tuple[str, ...] = HUMAN_METRICS) -> dict:
    counter: Counter[str] = Counter()
    examples: dict[str, dict] = {}
    for row in rows:
        for metric in metric_names:
            scores = [_coerce_score(row.get(f"a1_{metric}")), _coerce_score(row.get(f"a2_{metric}"))]
            scores = [score for score in scores if score is not None]
            threshold = 3.0 if metric == "citation_correctness" else 2.0
            if scores and mean(scores) <= threshold:
                _add_error(counter, examples, f"low_human_{metric}", row)
    return _error_payload(counter, examples, denominator=len(rows), denominator_label="human_eval_samples")


def _error_payload(counter: Counter[str], examples: dict[str, dict], denominator: int, denominator_label: str) -> dict:
    total = max(denominator, 1)
    return {
        "denominator": denominator,
        "denominator_label": denominator_label,
        "counts": dict(sorted(counter.items())),
        "rates": {key: round(value / total, 4) for key, value in sorted(counter.items())},
        "examples": examples,
    }


def _merge_error_categories(retrieval_payload: dict, generation_payload: dict) -> dict:
    counter = Counter(retrieval_payload.get("counts", {}))
    counter.update(generation_payload.get("counts", {}))
    examples = {**retrieval_payload.get("examples", {}), **generation_payload.get("examples", {})}
    total = max(retrieval_payload.get("denominator", 0), generation_payload.get("denominator", 0), 1)
    return {
        "total_scored_samples": generation_payload.get("denominator", 0),
        "total_retrieval_samples": retrieval_payload.get("denominator", 0),
        "counts": dict(sorted(counter.items())),
        "rates": {key: round(value / total, 4) for key, value in sorted(counter.items())},
        "examples": examples,
    }


def _categorize_errors(answer_details: list[dict], retrieval_details: list[dict]) -> dict:
    counter: Counter[str] = Counter()
    examples: dict[str, dict] = {}
    for item in retrieval_details:
        if not item.get("gold_in_index"):
            _add_error(counter, examples, "missing_gold_in_index", item)
        if item.get("hit_rank") is None:
            _add_error(counter, examples, "retrieval_miss", item)
    for item in answer_details:
        prediction_text = str(item.get("prediction_text", item.get("prediction", ""))).strip()
        gold_length = float(item.get("gold_length", 0.0) or 0.0)
        prediction_length = float(item.get("prediction_length", len(prediction_text)) or 0.0)
        if float(item.get("faithfulness_score", 0.0)) < 0.35:
            _add_error(counter, examples, "low_grounding_proxy", item)
        if float(item.get("token_f1", 0.0)) < 0.35 and float(item.get("rouge_l", 0.0)) < 0.3:
            _add_error(counter, examples, "weak_lexical_match", item)
        if float(item.get("citation_presence", 0.0)) < 1.0 or float(item.get("citation_correctness", 1.0)) < 0.5:
            _add_error(counter, examples, "wrong_or_weak_citation_proxy", item)
        if _is_refusal(prediction_text):
            _add_error(counter, examples, "over_refusal_candidate", item)
        if not _is_refusal(prediction_text) and float(item.get("faithfulness_score", 1.0)) < 0.2:
            _add_error(counter, examples, "under_refusal_candidate", item)
        if gold_length > 0 and prediction_length > gold_length * 1.25:
            _add_error(counter, examples, "verbose_answer_candidate", item)
        if float(item.get("directness_score", 1.0)) < 0.5:
            _add_error(counter, examples, "indirect_answer_proxy", item)
    total = max(len(answer_details), len(retrieval_details), 1)
    return {
        "total_scored_samples": len(answer_details),
        "total_retrieval_samples": len(retrieval_details),
        "counts": dict(sorted(counter.items())),
        "rates": {key: round(value / total, 4) for key, value in sorted(counter.items())},
        "examples": examples,
    }


def _add_error(counter: Counter[str], examples: dict[str, dict], category: str, item: dict) -> None:
    counter[category] += 1
    if category not in examples:
        examples[category] = _compact_error_example(item, category)


def _compact_error_example(item: dict, category: str) -> dict:
    retrieved = item.get("retrieved") or []
    prediction = str(item.get("prediction_text", item.get("prediction", ""))).replace("\n", " ").strip()
    return {
        "category": category,
        "question": item.get("question", ""),
        "gold_cids": item.get("gold_cids", []),
        "gold_evidence": item.get("gold_evidence", []),
        "gold_answer": str(item.get("gold_answer", ""))[:700],
        "retrieved_evidence": retrieved[:3],
        "prediction": prediction[:900],
        "hit_rank": item.get("hit_rank"),
    }


def _is_refusal(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in ("toi khong biet", "khong du can cu", "tôi không biết", "không đủ căn cứ"))


def _metric_float(payload: dict, key: str, default: float) -> float:
    value = payload.get(key, default)
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _build_human_eval_sample(answer_details: list[dict], retrieval_details: list[dict], sample_size: int) -> list[dict]:
    by_question = {item.get("question"): item for item in retrieval_details}
    candidates = []
    for index, item in enumerate(answer_details):
        retrieval = by_question.get(item.get("question"), {})
        tags = _human_eval_tags(item, retrieval)
        candidates.append((len(tags), index, item, retrieval, tags))
    if len(candidates) < sample_size:
        known_questions = {item.get("question") for _, _, item, _, _ in candidates}
        for index, retrieval in enumerate(retrieval_details):
            if retrieval.get("question") in known_questions:
                continue
            tags = _human_eval_tags({}, retrieval)
            candidates.append((len(tags), len(candidates) + index, {}, retrieval, tags))
    candidates.sort(key=lambda row: (-row[0], row[1]))
    selected = candidates[:sample_size]
    rows: list[dict] = []
    for row_id, (_, _, answer, retrieval, tags) in enumerate(selected, start=1):
        retrieved = retrieval.get("retrieved") or []
        prediction = str(answer.get("prediction_text", answer.get("prediction", ""))).strip()
        rows.append(
            {
                "id": f"human-{row_id:03d}",
                "tags": ";".join(tags),
                "question": answer.get("question") or retrieval.get("question", ""),
                "gold_answer": answer.get("gold_answer", ""),
                "gold_cids": ";".join(retrieval.get("gold_cids", [])),
                "gold_evidence": "\n\n".join(
                    f"cid={item.get('cid')} {item.get('snippet', '')}"
                    for item in (retrieval.get("gold_evidence") or [])[:5]
                ),
                "gold_evidence_available": retrieval.get("gold_in_index"),
                "hit_rank": retrieval.get("hit_rank"),
                "retrieved_evidence": "\n\n".join(
                    f"[{item.get('rank')}] cid={item.get('cid')} {item.get('snippet', '')}" for item in retrieved[:5]
                ),
                "prediction": prediction,
                "citations": json.dumps(_extract_citations(answer.get("prediction")), ensure_ascii=False),
                **_blank_human_eval_fields(),
            }
        )
    return rows


def _build_end_to_end_human_eval_sample(answer_details: list[dict], sample_size: int) -> list[dict]:
    candidates = []
    for index, item in enumerate(answer_details):
        if item.get("retrieval") or item.get("evidence_mode") == "retrieved_context":
            tags = _human_eval_tags(item, {})
            if _metric_float(item, "citation_correctness", 0.0) >= 0.9 and _metric_float(item, "format_compliance", 1.0) < 0.1:
                tags.append("proxy_citation_high_low_format")
            candidates.append((len(set(tags)), index, item, sorted(set(tags))))
    candidates.sort(key=lambda row: (-row[0], row[1]))
    rows: list[dict] = []
    for row_id, (_, _, answer, tags) in enumerate(candidates[:sample_size], start=1):
        retrieval = answer.get("retrieval") or {}
        retrieved = retrieval.get("retrieved") or answer.get("retrieved") or []
        rows.append(
            {
                "id": f"e2e-human-{row_id:03d}",
                "tags": ";".join(tags or ["routine"]),
                "question": answer.get("question", ""),
                "gold_answer": answer.get("gold_answer", ""),
                "gold_evidence": "",
                "retrieved_evidence": "\n\n".join(
                    f"[{item.get('rank')}] cid={item.get('cid')} {item.get('snippet', '')}" for item in retrieved[:5]
                ),
                "prediction": str(answer.get("prediction_text", answer.get("prediction", ""))).strip(),
                "citations": json.dumps(_extract_citations(answer.get("prediction")), ensure_ascii=False),
                "automatic_citation_correctness_proxy": answer.get("citation_correctness"),
                "automatic_faithfulness_proxy": answer.get("faithfulness_score"),
                "automatic_format_compliance": answer.get("format_compliance"),
                **_blank_end_to_end_human_eval_fields(),
            }
        )
    return rows


def _human_eval_tags(answer: dict, retrieval: dict) -> list[str]:
    tags: list[str] = []
    if retrieval and retrieval.get("hit_rank") is None:
        tags.append("retrieval_miss")
    if _metric_float(answer, "faithfulness_score", 1.0) < 0.35:
        tags.append("low_grounding")
    if _metric_float(answer, "citation_presence", 1.0) < 1.0 or _metric_float(answer, "citation_correctness", 1.0) < 0.5:
        tags.append("weak_citation")
    gold_length = _metric_float(answer, "gold_length", 0.0)
    prediction_length = _metric_float(answer, "prediction_length", 0.0)
    if gold_length > 0 and prediction_length > gold_length * 1.25:
        tags.append("verbose")
    if _metric_float(answer, "directness_score", 1.0) < 0.5:
        tags.append("indirect")
    if _is_refusal(str(answer.get("prediction_text", answer.get("prediction", "")))):
        tags.append("refusal")
    return tags or ["routine"]


def _extract_citations(prediction: object) -> list:
    if isinstance(prediction, dict):
        citations = prediction.get("citations") or []
        return citations if isinstance(citations, list) else [citations]
    return []


def _blank_human_eval_fields(metric_names: tuple[str, ...] = HUMAN_METRICS) -> dict:
    fields = {}
    for annotator in ("a1", "a2"):
        for metric in metric_names:
            fields[f"{annotator}_{metric}"] = ""
        fields[f"{annotator}_notes"] = ""
    return fields


def _blank_end_to_end_human_eval_fields() -> dict:
    fields = _blank_human_eval_fields(HUMAN_METRICS)
    for annotator in ("a1", "a2"):
        fields[f"{annotator}_citation_support_score"] = ""
        fields[f"{annotator}_unsupported_claim_notes"] = ""
    return fields


def _write_human_eval_jsonl(path: Path, rows: list[dict]) -> bool:
    if path.exists() and _jsonl_has_annotations(path):
        return False
    save_jsonl(path, rows)
    return True


def _write_human_eval_csv(path: Path, rows: list[dict]) -> bool:
    if path.exists() and _csv_has_annotations(path):
        return False
    if not rows:
        path.write_text("", encoding="utf-8")
        return True
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return True


def _write_tsv(path: Path, rows: list[dict], metrics: tuple[str, ...] = HUMAN_METRICS) -> bool:
    if path.exists() and _delimited_has_annotations(path, metrics):
        return False
    if not rows:
        path.write_text("", encoding="utf-8")
        return True
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), dialect=csv.excel_tab)
        writer.writeheader()
        writer.writerows(rows)
    return True


def _delimited_has_annotations(path: Path, metrics: tuple[str, ...]) -> bool:
    try:
        return any(_row_has_annotation(row, metrics=metrics) for row in _read_delimited_rows(path))
    except OSError:
        return False


def _csv_has_annotations(path: Path) -> bool:
    try:
        return any(_row_has_annotation(row) for row in _read_delimited_rows(path))
    except OSError:
        return False


def _jsonl_has_annotations(path: Path) -> bool:
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                if _row_has_annotation(json.loads(line)):
                    return True
    except (OSError, json.JSONDecodeError):
        return False
    return False


def _row_has_annotation(row: dict, metrics: tuple[str, ...] = HUMAN_METRICS) -> bool:
    for annotator in ("a1", "a2"):
        for metric in metrics:
            if _coerce_score(row.get(f"{annotator}_{metric}")) is not None:
                return True
    return False



def _read_delimited_rows(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8-sig")
    first_line = text.splitlines()[0] if text.splitlines() else ""
    if "\t" in first_line:
        dialect = csv.excel_tab
    else:
        sample = text[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;")
        except csv.Error:
            dialect = csv.excel
    return list(csv.DictReader(io.StringIO(text), dialect=dialect))

def _load_or_initialize_human_eval(path: str | None, sample_rows: list[dict]) -> dict:
    if not path:
        return {
            "status": "pending_annotations",
            "evaluation_label": "Human Evaluation",
            "samples": len(sample_rows),
            "annotators": 2,
            "independent": True,
            "ai_assisted": False,
            "calibration": "3-5 pilot examples",
            "rubric_scale": "1-5",
            "metrics": list(HUMAN_METRICS),
            "notes": f"Fill reports/human_eval_sample_{len(sample_rows)}.csv or pass --human-eval with completed annotations.",
        }
    csv_path = Path(path)
    if not csv_path.exists():
        return {"status": "annotation_file_not_found", "path": str(csv_path), "samples": len(sample_rows)}
    rows = _read_delimited_rows(csv_path)
    return _aggregate_human_eval(rows, str(csv_path))


def _load_or_initialize_end_to_end_human_eval(path: str | None, sample_rows: list[dict]) -> dict:
    if not path:
        return {
            "status": "pending_annotations",
            "evaluation_label": "End-to-End Human Evaluation",
            "samples": len(sample_rows),
            "annotators": 2,
            "independent": True,
            "ai_assisted": False,
            "calibration": "3-5 pilot examples",
            "rubric_scale": "1-5",
            "metric_names": list(END_TO_END_HUMAN_METRICS),
            "notes": f"Fill reports/end_to_end_human_eval_sample_{len(sample_rows)}.tsv or pass --end-to-end-human-eval with completed annotations.",
        }
    active = Path(path)
    if not active.exists():
        return {"status": "annotation_file_not_found", "path": str(active), "samples": len(sample_rows)}
    rows = _read_delimited_rows(active)
    return _aggregate_human_eval(rows, str(active), metric_names=END_TO_END_HUMAN_METRICS, label="End-to-End Human Evaluation")


def _aggregate_human_eval(rows: list[dict], source: str, metric_names: tuple[str, ...] = HUMAN_METRICS, label: str = "Human Evaluation") -> dict:
    summary: dict[str, object] = {
        "status": "scored",
        "evaluation_label": label,
        "source": source,
        "samples": len(rows),
        "annotators": 2,
        "independent": True,
        "ai_assisted": False,
        "calibration": "3-5 pilot examples",
        "rubric_scale": "1-5",
        "metric_names": list(metric_names),
    }
    metric_summary = {}
    per_annotator = {"a1": {}, "a2": {}}
    agreement = {}
    score_distribution = {}
    for metric in metric_names:
        values = []
        paired = []
        for annotator in ("a1", "a2"):
            scores = [_coerce_score(row.get(f"{annotator}_{metric}")) for row in rows]
            scores = [score for score in scores if score is not None]
            per_annotator[annotator][metric] = _score_stats(scores)
            values.extend(scores)
        for row in rows:
            a1 = _coerce_score(row.get(f"a1_{metric}"))
            a2 = _coerce_score(row.get(f"a2_{metric}"))
            if a1 is not None and a2 is not None:
                paired.append((a1, a2))
        metric_summary[metric] = _score_stats(values)
        agreement[metric] = _agreement_stats(paired)
        score_distribution[metric] = _score_distribution(values)
    summary["metrics"] = metric_summary
    summary["per_annotator"] = per_annotator
    summary["agreement"] = agreement
    summary["score_distribution"] = score_distribution
    return summary


def _coerce_score(value: object) -> float | None:
    try:
        score = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if score < 1 or score > 5:
        return None
    return score


def _score_stats(scores: list[float]) -> dict:
    if not scores:
        return {"n": 0, "mean": None, "std": None}
    return {"n": len(scores), "mean": round(mean(scores), 4), "std": round(pstdev(scores), 4)}


def _score_distribution(scores: list[float]) -> dict:
    counts = {str(score): 0 for score in range(1, 6)}
    for score in scores:
        bucket = int(score)
        if 1 <= bucket <= 5:
            counts[str(bucket)] += 1
    total = sum(counts.values())
    denominator = max(total, 1)
    return {
        "n": total,
        "score_1": counts["1"],
        "score_2": counts["2"],
        "score_3": counts["3"],
        "score_4": counts["4"],
        "score_5": counts["5"],
        "pass_rate_ge4": round((counts["4"] + counts["5"]) / denominator, 4),
        "weak_fail_rate_le3": round((counts["1"] + counts["2"] + counts["3"]) / denominator, 4),
    }


def _agreement_stats(pairs: list[tuple[float, float]]) -> dict:
    if not pairs:
        return {"n": 0, "mean_abs_diff": None, "exact_agreement": None, "within_1_agreement": None}
    abs_diffs = [abs(a - b) for a, b in pairs]
    return {
        "n": len(pairs),
        "mean_abs_diff": round(mean(abs_diffs), 4),
        "exact_agreement": round(sum(1 for diff in abs_diffs if diff == 0) / len(abs_diffs), 4),
        "within_1_agreement": round(sum(1 for diff in abs_diffs if diff <= 1) / len(abs_diffs), 4),
    }


def _write_human_eval_summary(report_dir: Path, summary: dict) -> None:
    save_json(report_dir / "human_eval_summary.json", summary)
    (report_dir / "human_eval_summary.md").write_text(_render_human_eval_markdown(summary), encoding="utf-8")


def _write_end_to_end_human_eval_summary(report_dir: Path, summary: dict) -> None:
    save_json(report_dir / "end_to_end_human_eval_summary.json", summary)
    (report_dir / "end_to_end_human_eval_summary.md").write_text(_render_human_eval_markdown(summary), encoding="utf-8")


def _select_case_studies(answer_details: list[dict], retrieval_details: list[dict]) -> list[dict]:
    retrieval_by_question = {item.get("question"): item for item in retrieval_details}
    cases: list[dict] = []
    success = next(
        (
            item
            for item in answer_details
            if float(item.get("faithfulness_score", 0.0)) >= 0.75
            and float(item.get("citation_presence", 0.0)) >= 1.0
            and retrieval_by_question.get(item.get("question"), {}).get("hit_rank") in (1, 2, 3)
        ),
        None,
    )
    retrieval_failure = next((item for item in retrieval_details if item.get("hit_rank") is None), None)
    generation_failure = next(
        (
            item
            for item in answer_details
            if float(item.get("faithfulness_score", 1.0)) < 0.35 or float(item.get("citation_presence", 1.0)) < 1.0
        ),
        None,
    )
    if success:
        cases.append(_case_from_answer("success_case", success, retrieval_by_question.get(success.get("question"), {})))
    if retrieval_failure:
        cases.append(_case_from_retrieval("retrieval_failure", retrieval_failure))
    if generation_failure:
        cases.append(
            _case_from_answer(
                "generation_or_citation_failure",
                generation_failure,
                retrieval_by_question.get(generation_failure.get("question"), {}),
            )
        )
    return cases[:3]


def _case_from_answer(label: str, answer: dict, retrieval: dict) -> dict:
    return {
        "case": label,
        "question": answer.get("question", ""),
        "gold_answer": str(answer.get("gold_answer", ""))[:900],
        "gold_evidence": (retrieval.get("gold_evidence") or [])[:3],
        "retrieved_evidence": (retrieval.get("retrieved") or [])[:3],
        "prediction": str(answer.get("prediction_text", answer.get("prediction", ""))).replace("\n", " ").strip()[:1200],
        "automatic_signals": {
            "hit_rank": retrieval.get("hit_rank"),
            "faithfulness_score": answer.get("faithfulness_score"),
            "citation_presence": answer.get("citation_presence"),
            "citation_correctness": answer.get("citation_correctness"),
            "directness_score": answer.get("directness_score"),
        },
    }


def _case_from_retrieval(label: str, retrieval: dict) -> dict:
    return {
        "case": label,
        "question": retrieval.get("question", ""),
        "gold_cids": retrieval.get("gold_cids", []),
        "gold_evidence": (retrieval.get("gold_evidence") or [])[:3],
        "retrieved_evidence": (retrieval.get("retrieved") or [])[:3],
        "automatic_signals": {"hit_rank": retrieval.get("hit_rank"), "gold_in_index": retrieval.get("gold_in_index")},
    }


def _render_markdown(payload: dict) -> str:
    lines = [
        "# Paper Experiments Report",
        "",
        "All grounding-oriented answer metrics in this report are proxy metrics, not legal-expert judgments.",
        "",
        "## Dataset Statistics",
        "",
        _kv_table(payload["dataset_stats"]),
        "",
        "## Retrieval Results",
        "",
        _metric_table([payload["retrieval"]], include_variant=False),
        "",
        "## Retrieval Ablation",
        "",
        _metric_table(payload["retrieval_ablations"], include_variant=True),
        "",
        _retrieval_variant_notes(),
        "",
        "## Generation Results",
        "",
        _kv_table(payload["answer_generation"]),
        "",
        "## End-to-End RAG Generation",
        "",
        _retrieved_generation_comparison_table(
            payload.get("retrieved_answer_generation", {}),
            payload.get("retrieved_prompt_only_generation", {}),
        ),
        "",
        "## Schema Prompting Before/After",
        "",
        _schema_prompting_table(
            payload.get("retrieved_answer_generation", {}),
            payload.get("retrieved_schema_generation", {}),
        ),
        "",
        "## QA-Memory Leakage Audit",
        "",
        _qa_memory_leakage_table(payload.get("qa_memory_leakage", {})),
        "",
        "## Generation Baselines",
        "",
        _generation_baselines_table(payload.get("generation_baselines", {})),
        "",
        "## Human Evaluation",
        "",
        _render_human_eval_markdown(payload["human_evaluation"]),
        "",
        "## End-to-End Human Evaluation",
        "",
        _render_human_eval_markdown(payload.get("end_to_end_human_evaluation", {})),
        "",
        f"## Retrieval Error Categories (N={payload['retrieval_error_categories'].get('denominator', 0)})",
        "",
        _error_table(payload["retrieval_error_categories"]),
        "",
        f"## Generation Error Categories (N={payload['generation_error_categories'].get('denominator', 0)})",
        "",
        _error_table(payload["generation_error_categories"]),
        "",
        f"## Human Evaluation Error Categories (N={payload['human_error_categories'].get('denominator', 0)})",
        "",
        _error_table(payload["human_error_categories"]),
        "",
        "## Case Studies",
        "",
        _case_study_markdown(payload.get("case_studies", [])),
        "",
        "## Notes",
        "",
    ]
    lines.extend(f"- {note}" for note in payload.get("notes", []))
    return "\n".join(lines).strip() + "\n"


def _retrieved_generation_comparison_table(qlora_payload: dict, prompt_only_payload: dict) -> str:
    rows = [row for row in (qlora_payload, prompt_only_payload) if row]
    if not rows:
        return _retrieved_generation_table({})
    columns = [
        "variant",
        "evidence_mode",
        "retrieval_variant",
        "retrieval_top_k",
        "samples",
        "token_f1",
        "rouge_l",
        "citation_presence",
        "format_compliance",
        "faithfulness_score",
        "directness_score",
        "citation_correctness",
        "refusal_quality",
    ]
    lines = ["| " + " | ".join(columns) + " |", "|" + "|".join("---" for _ in columns) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(column, "")) for column in columns) + " |")
    if not prompt_only_payload:
        lines.extend(["", "_Prompt-only retrieved-context baseline is missing. Run `PYTHONPATH=. python scripts/eval_answer_generation.py --limit 200 --max-new-tokens 256 --variant qwen_prompt_only --evidence-mode retrieved_context --retrieval-top-k 5`._"])
    return "\n".join(lines)


def _schema_prompting_table(default_payload: dict, schema_payload: dict) -> str:
    if not default_payload and not schema_payload:
        return "_No schema prompting reports found._"
    rows = []
    if default_payload:
        rows.append({**default_payload, "run": "qwen_qlora retrieved default"})
    if schema_payload:
        rows.append({**schema_payload, "run": "qwen_qlora retrieved schema"})
    columns = ["run", "samples", "token_f1", "rouge_l", "citation_presence", "format_compliance", "faithfulness_score", "directness_score", "citation_correctness"]
    lines = ["| " + " | ".join(columns) + " |", "|" + "|".join("---" for _ in columns) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(column, "")) for column in columns) + " |")
    if not schema_payload:
        lines.extend(["", "_Schema prompting report is missing; do not claim format-compliance improvement until the 200-sample schema run exists._"])
    elif int(schema_payload.get("samples", 0) or 0) < 200:
        lines.extend(["", f"_Schema prompting has only {int(schema_payload.get('samples', 0) or 0)} smoke samples; do not claim format-compliance improvement as a paper-scale result._"])
    return "\n".join(lines)


def _retrieved_generation_table(payload: dict) -> str:
    if not payload:
        return "_No retrieved-context generation report found. Run `PYTHONPATH=. python scripts/eval_answer_generation.py --limit 200 --max-new-tokens 256 --variant qwen_qlora --evidence-mode retrieved_context --retrieval-top-k 5`._"
    columns = [
        "variant",
        "evidence_mode",
        "retrieval_variant",
        "retrieval_top_k",
        "samples",
        "token_f1",
        "rouge_l",
        "citation_presence",
        "format_compliance",
        "faithfulness_score",
        "directness_score",
        "citation_correctness",
        "refusal_quality",
    ]
    lines = ["| " + " | ".join(columns) + " |", "|" + "|".join("---" for _ in columns) + "|"]
    lines.append("| " + " | ".join(str(payload.get(column, "")) for column in columns) + " |")
    return "\n".join(lines)


def _qa_memory_leakage_table(payload: dict) -> str:
    if not payload:
        return "_No QA-memory leakage audit found. Run `PYTHONPATH=. python scripts/audit_qa_memory_leakage.py --eval-dataset data/processed/thangvip_legalqa/test.jsonl --near-threshold 0.9`._"
    rows = [
        ("Eval questions", payload.get("eval_questions", 0)),
        ("QA-memory questions", payload.get("qa_memory_questions", 0)),
        ("Exact duplicates", payload.get("exact_duplicates", 0)),
        ("Normalized duplicates", payload.get("normalized_duplicates", 0)),
        (f"Near duplicates >= {payload.get('near_threshold', '')}", payload.get("near_duplicates", 0)),
        ("Max similarity", payload.get("max_similarity", 0.0)),
    ]
    lines = ["| Metric | Value |", "|---|---:|"]
    lines.extend(f"| {label} | {value} |" for label, value in rows)
    return "\n".join(lines)


def _kv_table(payload: dict) -> str:
    if not payload:
        return "_No data available._"
    lines = ["| Field | Value |", "|---|---|"]
    for key, value in payload.items():
        lines.append(f"| `{key}` | {value} |")
    return "\n".join(lines)


def _metric_table(rows: list[dict], include_variant: bool) -> str:
    columns = [
        "variant",
        "samples",
        "top_k",
        "gold_coverage_in_index",
        "recall@1",
        "recall@5",
        "recall@10",
        "recall@20",
        "mrr",
        "ndcg@10",
        "conditional_mrr",
    ]
    if not include_variant:
        columns = columns[1:]
    lines = ["| " + " | ".join(columns) + " |", "|" + "|".join("---" for _ in columns) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(column, "")) for column in columns) + " |")
    return "\n".join(lines)


def _retrieval_variant_notes() -> str:
    return "\n".join(
        [
            "- **BM25 (hashing):** lexical retrieval with a hashed word 1-2 gram vector space and cosine scoring; this is the lexical channel used inside the hybrid fuser, not textbook BM25.",
            "- **BM25 (Okapi):** true Okapi BM25 (Lucene variant, k1=1.5, b=0.75) over the same chunk corpus, reported as the standard lexical baseline.",
            "- **Dense:** semantic retrieval using neural embeddings and a normalized FAISS cosine index.",
            "- **Hybrid:** combines lexical, dense, and ranking signals to balance exact matches with semantic recall.",
            "- **Hybrid + QA-memory:** uses similar questions to seed and boost related legal-document candidates.",
            "- **Cross-encoder reranker:** directly scores each question-passage pair from Hybrid + QA-memory candidates to improve final ranking; `_k100` widens the candidate pool from 50 to 100.",
            "- **nDCG@10:** binary-relevance nDCG over cid-deduplicated rankings, so repeated chunks of one citation are credited once.",
        ]
    )

def _error_table(payload: dict) -> str:
    counts = payload.get("counts", {})
    rates = payload.get("rates", {})
    if not counts:
        return "_No error categories found._"
    denominator = payload.get("denominator", payload.get("total_scored_samples") or payload.get("total_retrieval_samples") or "")
    count_label = f"Count / {denominator}" if denominator != "" else "Count"
    lines = [
        f"| Category | {count_label} | Rate | Question | Gold evidence/cids | Retrieved evidence | Prediction/error |",
        "|---|---:|---:|---|---|---|---|",
    ]
    examples = payload.get("examples", {})
    for category, count in counts.items():
        example = examples.get(category, {})
        question = _markdown_cell(example.get("question", ""), 150)
        gold = _markdown_cell(_gold_summary(example), 180)
        retrieved = _markdown_cell(_retrieved_summary(example.get("retrieved_evidence") or []), 220)
        prediction = _markdown_cell(example.get("prediction") or category, 220)
        lines.append(
            f"| `{category}` | {count} | {rates.get(category, '')} | {question} | {gold} | {retrieved} | {prediction} |"
        )
    return "\n".join(lines)


def _gold_summary(example: dict) -> str:
    gold_answer = str(example.get("gold_answer", "")).strip()
    gold_evidence = example.get("gold_evidence") or []
    gold_cids = example.get("gold_cids") or []
    if gold_answer:
        return gold_answer
    if gold_evidence:
        return _retrieved_summary(gold_evidence)
    if gold_cids:
        return "gold_cids=" + ", ".join(str(cid) for cid in gold_cids)
    return ""


def _retrieved_summary(items: list[dict]) -> str:
    parts = []
    for item in items[:3]:
        snippet = str(item.get("snippet", "")).replace("\n", " ").strip()
        parts.append(f"rank {item.get('rank')} cid={item.get('cid')}: {snippet}")
    return " || ".join(parts)


def _markdown_cell(value: object, limit: int) -> str:
    text = str(value or "").replace("\n", " ").replace("|", "\\|").strip()
    if len(text) <= limit:
        return text
    return text[: max(limit - 3, 0)].rstrip() + "..."



def _generation_baselines_table(payload: dict) -> str:
    rows = payload.get("baselines") or []
    if not rows:
        return "_No generation baselines report found. Run `scripts/eval_answer_generation.py --variant all_baselines` to populate this table._"
    main_rows = [row for row in rows if not row.get("exclude_from_main_table")]
    columns = [
        "variant",
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
    ]
    lines = ["| " + " | ".join(columns) + " |", "|" + "|".join("---" for _ in columns) + "|"]
    for row in main_rows:
        lines.append("| " + " | ".join(str(row.get(column, "")) for column in columns) + " |")
    diagnostics = [row for row in rows if row.get("exclude_from_main_table") or row.get("diagnostic_note")]
    if diagnostics:
        lines.extend(["", "Diagnostic rows excluded from the main table:"])
        for row in diagnostics:
            lines.append(f"- `{row.get('variant')}`: {row.get('diagnostic_note') or row.get('status')}")
    return "\n".join(lines)

def _render_human_eval_markdown(summary: dict) -> str:
    status = summary.get("status", "unknown")
    if status != "scored":
        return _kv_table(summary)
    label = summary.get("evaluation_label", "Human Evaluation")
    independent = "independently" if summary.get("independent") is not False else "not independently"
    ai_clause = "no AI-assisted scoring" if summary.get("ai_assisted") is False else "AI-assisted scoring disclosed"
    calibration = summary.get("calibration", "3-5 pilot examples")
    lines = [
        f"Source: `{summary.get('source')}`",
        "",
        f"Disclosure: {summary.get('annotators', 2)} human annotators scored {independent} after short calibration ({calibration}); {ai_clause} is reported as {label}.",
        "",
        f"We evaluate {summary.get('samples', 0)} examples, each scored by two human annotators, resulting in {int(summary.get('samples', 0) or 0) * 2} annotation scores per metric.",
        "",
        "The annotators are not legal experts, so the evaluation should be interpreted as preliminary human assessment, not expert legal validation.",
        "",
        "Agreement values are descriptive statistics, not formal inter-annotator reliability coefficients.",
        "",
    ]
    metric_names = tuple(summary.get("metric_names") or HUMAN_METRICS)
    metrics = summary.get("metrics", {})
    agreement = summary.get("agreement", {})
    distribution = summary.get("score_distribution", {})
    if distribution:
        lines.extend(
            [
                "### Human Evaluation Compact Summary",
                "",
                "| Metric | Mean | Std | Exact Agree | Within-1 Agree | Pass >=4 | Weak/Fail <=3 |",
                "|---|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for metric in metric_names:
            metric_stats = metrics.get(metric, {})
            agreement_stats = agreement.get(metric, {})
            dist = distribution.get(metric, {})
            lines.append(
                "| "
                + " | ".join(
                    str(value)
                    for value in [
                        metric,
                        metric_stats.get("mean", ""),
                        metric_stats.get("std", ""),
                        agreement_stats.get("exact_agreement", ""),
                        agreement_stats.get("within_1_agreement", ""),
                        dist.get("pass_rate_ge4", ""),
                        dist.get("weak_fail_rate_le3", ""),
                    ]
                )
                + " |"
            )
        lines.extend(["", "### Human Evaluation Detailed Agreement", ""])
    lines.extend(
        [
            "| Metric | N | Mean | Std | Mean Abs Diff | Exact Agree | Within-1 Agree |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for metric in metric_names:
        metric_stats = metrics.get(metric, {})
        agreement_stats = agreement.get(metric, {})
        lines.append(
            "| "
            + " | ".join(
                str(value)
                for value in [
                    metric,
                    metric_stats.get("n", 0),
                    metric_stats.get("mean", ""),
                    metric_stats.get("std", ""),
                    agreement_stats.get("mean_abs_diff", ""),
                    agreement_stats.get("exact_agreement", ""),
                    agreement_stats.get("within_1_agreement", ""),
                ]
            )
            + " |"
        )
    if distribution:
        lines.extend(
            [
                "",
                "### Human Evaluation Score Distribution",
                "",
                "| Metric | N | Score 1 | Score 2 | Score 3 | Score 4 | Score 5 | Pass Rate >=4 | Weak/Fail Rate <=3 |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for metric in metric_names:
            row = distribution.get(metric, {})
            lines.append(
                "| "
                + " | ".join(
                    str(value)
                    for value in [
                        metric,
                        row.get("n", 0),
                        row.get("score_1", 0),
                        row.get("score_2", 0),
                        row.get("score_3", 0),
                        row.get("score_4", 0),
                        row.get("score_5", 0),
                        row.get("pass_rate_ge4", ""),
                        row.get("weak_fail_rate_le3", ""),
                    ]
                )
                + " |"
            )
    return "\n".join(lines)


def _case_study_markdown(cases: list[dict]) -> str:
    if not cases:
        return "_No case studies available._"
    lines = []
    for case in cases:
        lines.extend(
            [
                f"### {case.get('case', 'case')}",
                "",
                f"Question: {case.get('question', '')}",
                "",
                f"Gold/target: {str(case.get('gold_answer', case.get('gold_cids', '')))[:700]}",
                "",
                "Gold evidence:",
            ]
        )
        for item in case.get("gold_evidence", []):
            lines.append(f"- cid {item.get('cid')}: {item.get('snippet', '')[:350]}")
        lines.extend(["", "Retrieved evidence:"])
        for item in case.get("retrieved_evidence", []):
            lines.append(f"- rank {item.get('rank')}, cid {item.get('cid')}: {item.get('snippet', '')[:350]}")
        if case.get("prediction"):
            lines.extend(["", f"Prediction: {case.get('prediction', '')[:900]}"])
        lines.extend(["", f"Signals: `{json.dumps(case.get('automatic_signals', {}), ensure_ascii=False)}`", ""])
    return "\n".join(lines).strip()


if __name__ == "__main__":
    main()
