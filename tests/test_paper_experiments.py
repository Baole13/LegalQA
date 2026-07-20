from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from scripts.run_paper_experiments import (
    END_TO_END_HUMAN_METRICS,
    HUMAN_METRICS,
    _aggregate_human_eval,
    _build_end_to_end_human_eval_sample,
    _build_human_eval_sample,
    _categorize_generation_errors,
    _categorize_human_errors,
    _categorize_retrieval_errors,
    _generation_baselines_table,
    _metric_table,
    _normalize_generation_metrics,
    _qa_memory_leakage_table,
    _qa_memory_disabled,
    _render_human_eval_markdown,
    _retrieved_generation_comparison_table,
    _retrieved_generation_table,
    _schema_prompting_table,
    _select_main_retrieval_result,
    _write_human_eval_csv,
)


class DummyRetriever:
    def __init__(self):
        self.weights = {"qa_boost": 0.8, "bm25": 0.5}
        self.qa_config = {"top_k": 12, "seed_top_hits": 6}

    def _search_similar_questions(self, query, top_k=5):
        return [{"query": query, "top_k": top_k}]


def test_qa_memory_disabled_restores_retriever_state():
    retriever = DummyRetriever()
    pipeline = SimpleNamespace(artifacts=SimpleNamespace(retriever=retriever))
    with _qa_memory_disabled(pipeline):
        assert retriever._search_similar_questions("q") == []
        assert retriever.weights["qa_boost"] == 0.0
        assert retriever.qa_config["top_k"] == 0
        assert retriever.qa_config["seed_top_hits"] == 0

    assert retriever._search_similar_questions("q", top_k=2) == [{"query": "q", "top_k": 2}]
    assert retriever.weights == {"qa_boost": 0.8, "bm25": 0.5}
    assert retriever.qa_config == {"top_k": 12, "seed_top_hits": 6}


def test_build_human_eval_sample_has_two_annotator_rubric_fields():
    answer_details = [
        {
            "question": "Ai co tham quyen?",
            "gold_answer": "Bo truong.",
            "prediction_text": "Thu tuong.",
            "faithfulness_score": 0.1,
            "citation_presence": 0.0,
            "citation_correctness": 0.0,
            "directness_score": 0.4,
            "prediction_length": 20,
            "gold_length": 10,
        }
    ]
    retrieval_details = [
        {
            "question": "Ai co tham quyen?",
            "gold_cids": ["123"],
            "gold_in_index": True,
            "hit_rank": None,
            "retrieved": [{"rank": 1, "cid": "999", "snippet": "Sai can cu"}],
        }
    ]

    rows = _build_human_eval_sample(answer_details, retrieval_details, sample_size=1)

    assert len(rows) == 1
    assert rows[0]["id"] == "human-001"
    assert "retrieval_miss" in rows[0]["tags"]
    for annotator in ("a1", "a2"):
        for metric in HUMAN_METRICS:
            assert f"{annotator}_{metric}" in rows[0]


def test_aggregate_human_eval_reports_means_and_agreement():
    rows = [
        {
            "a1_legal_correctness": "5",
            "a2_legal_correctness": "4",
            "a1_grounding": "4",
            "a2_grounding": "4",
            "a1_citation_correctness": "3",
            "a2_citation_correctness": "2",
            "a1_directness": "5",
            "a2_directness": "5",
            "a1_refusal": "1",
            "a2_refusal": "1",
        }
    ]

    summary = _aggregate_human_eval(rows, "annotations.csv")

    assert summary["status"] == "scored"
    assert summary["evaluation_label"] == "Human Evaluation"
    assert summary["independent"] is True
    assert summary["ai_assisted"] is False
    assert summary["metrics"]["legal_correctness"]["mean"] == 4.5
    assert summary["agreement"]["legal_correctness"]["mean_abs_diff"] == 1.0
    assert summary["agreement"]["directness"]["exact_agreement"] == 1.0
    assert summary["score_distribution"]["legal_correctness"]["score_4"] == 1
    assert summary["score_distribution"]["legal_correctness"]["score_5"] == 1
    assert summary["score_distribution"]["legal_correctness"]["pass_rate_ge4"] == 1.0
    assert summary["score_distribution"]["citation_correctness"]["weak_fail_rate_le3"] == 1.0

def test_metric_table_uses_paper_retrieval_columns():
    table = _metric_table(
        [
            {
                "variant": "full",
                "samples": 300,
                "top_k": 20,
                "gold_coverage_in_index": 0.9,
                "recall@1": 0.1,
                "recall@3": 0.2,
                "recall@5": 0.3,
                "recall@8": 0.4,
                "recall@10": 0.5,
                "recall@20": 0.6,
                "mrr": 0.2,
                "conditional_mrr": 0.22,
            }
        ],
        include_variant=True,
    )

    header = table.splitlines()[0]
    assert "recall@1" in header
    assert "recall@5" in header
    assert "recall@10" in header
    assert "recall@20" in header
    assert "recall@3" not in header
    assert "recall@8" not in header


def test_write_human_eval_csv_preserves_completed_annotations(tmp_path):
    path = tmp_path / "human_eval_sample_75.csv"
    path.write_text(
        "id,a1_legal_correctness,a2_legal_correctness\n"
        "human-001,5,4\n",
        encoding="utf-8",
    )

    written = _write_human_eval_csv(
        path,
        [
            {
                "id": "human-001",
                "a1_legal_correctness": "",
                "a2_legal_correctness": "",
            }
        ],
    )

    assert written is False
    assert "5,4" in path.read_text(encoding="utf-8")



def test_normalize_generation_metrics_renames_structure_score():
    payload = {
        "samples": 1,
        "structure_score": 0.25,
        "details": [{"question": "q", "structure_score": 0.5}],
    }

    normalized = _normalize_generation_metrics(payload)

    assert normalized["format_compliance"] == 0.25
    assert "structure_score" not in normalized
    assert normalized["details"][0]["format_compliance"] == 0.5
    assert "structure_score" not in normalized["details"][0]


def test_error_category_denominators_are_split_by_source():
    retrieval = _categorize_retrieval_errors([
        {"question": "q1", "gold_in_index": True, "hit_rank": 7},
        {"question": "q2", "gold_in_index": False, "hit_rank": None},
    ])
    generation = _categorize_generation_errors([
        {
            "question": "q1",
            "prediction_text": "khong ro",
            "faithfulness_score": 0.1,
            "token_f1": 0.1,
            "rouge_l": 0.1,
            "citation_presence": 0.0,
            "format_compliance": 0.0,
            "directness_score": 0.4,
            "gold_length": 10,
            "prediction_length": 20,
        }
    ])
    human = _categorize_human_errors([
        {
            "question": "q1",
            "a1_legal_correctness": "2",
            "a2_legal_correctness": "2",
            "a1_grounding": "5",
            "a2_grounding": "5",
        }
    ])

    assert retrieval["denominator"] == 2
    assert retrieval["denominator_label"] == "retrieval_samples"
    assert retrieval["counts"]["retrieval_miss"] == 1
    assert retrieval["counts"]["low_rank_after_top5"] == 1
    assert generation["denominator"] == 1
    assert generation["denominator_label"] == "generation_samples"
    assert generation["counts"]["low_format_compliance"] == 1
    assert human["denominator"] == 1
    assert human["denominator_label"] == "human_eval_samples"
    assert human["counts"]["low_human_legal_correctness"] == 1


def test_select_main_retrieval_prefers_cross_encoder_row():
    fallback = {"variant": "full", "recall@5": 0.51}
    selected = _select_main_retrieval_result(
        [
            {"variant": "full_without_model_reranker", "recall@5": 0.51},
            {"variant": "full_with_cross_encoder_reranker", "recall@5": 0.6133},
        ],
        fallback=fallback,
    )

    assert selected["variant"] == "full_with_cross_encoder_reranker"
    assert selected["recall@5"] == 0.6133




def test_qa_memory_leakage_table_renders_duplicate_counts():
    table = _qa_memory_leakage_table(
        {
            "eval_questions": 1458,
            "qa_memory_questions": 89261,
            "near_threshold": 0.9,
            "exact_duplicates": 0,
            "normalized_duplicates": 0,
            "near_duplicates": 2,
            "max_similarity": 0.9388,
        }
    )

    assert "Exact duplicates | 0" in table
    assert "Near duplicates >= 0.9 | 2" in table
    assert "Max similarity | 0.9388" in table

def test_retrieved_generation_table_renders_end_to_end_rag_metrics():
    table = _retrieved_generation_table(
        {
            "variant": "qwen_qlora",
            "evidence_mode": "retrieved_context_llm",
            "retrieval_variant": "full_with_cross_encoder_reranker",
            "retrieval_top_k": 5,
            "samples": 200,
            "token_f1": 0.42,
            "rouge_l": 0.31,
            "format_compliance": 0.2,
        }
    )

    assert "retrieved_context_llm" in table
    assert "full_with_cross_encoder_reranker" in table
    assert "token_f1" in table


def test_retrieved_generation_table_tells_user_when_artifact_missing():
    table = _retrieved_generation_table({})

    assert "No retrieved-context generation report found" in table
    assert "--evidence-mode retrieved_context" in table

def test_retrieved_generation_comparison_table_includes_prompt_only_baseline():
    table = _retrieved_generation_comparison_table(
        {
            "variant": "qwen_qlora",
            "evidence_mode": "retrieved_context",
            "retrieval_variant": "full_with_cross_encoder_reranker",
            "retrieval_top_k": 5,
            "samples": 200,
            "token_f1": 0.55,
        },
        {
            "variant": "qwen_prompt_only",
            "evidence_mode": "retrieved_context",
            "retrieval_variant": "full_with_cross_encoder_reranker",
            "retrieval_top_k": 5,
            "samples": 200,
            "token_f1": 0.5,
        },
    )

    assert "qwen_qlora" in table
    assert "qwen_prompt_only" in table
    assert "Prompt-only retrieved-context baseline is missing" not in table


def test_schema_prompting_table_renders_before_after_and_missing_note():
    missing = _schema_prompting_table({"samples": 200, "format_compliance": 0.002}, {})
    assert "qwen_qlora retrieved default" in missing
    assert "Schema prompting report is missing" in missing

    smoke = _schema_prompting_table(
        {"samples": 200, "format_compliance": 0.002, "token_f1": 0.55},
        {"samples": 5, "format_compliance": 0.0, "token_f1": 0.38},
    )
    assert "only 5 smoke samples" in smoke

    table = _schema_prompting_table(
        {"samples": 200, "format_compliance": 0.002, "token_f1": 0.55},
        {"samples": 200, "format_compliance": 0.42, "token_f1": 0.53},
    )
    assert "qwen_qlora retrieved schema" in table
    assert "0.42" in table
    assert "Schema prompting report is missing" not in table
    assert "smoke samples" not in table


def test_build_end_to_end_human_eval_sample_uses_retrieved_context_and_citation_support_fields():
    rows = _build_end_to_end_human_eval_sample(
        [
            {
                "question": "q",
                "gold_answer": "a",
                "prediction_text": "p",
                "evidence_mode": "retrieved_context",
                "retrieval": {"retrieved": [{"rank": 1, "cid": "c1", "snippet": "evidence"}]},
                "prediction": {"citations": [{"cid": "c1"}]},
                "citation_correctness": 1.0,
                "faithfulness_score": 0.9,
                "format_compliance": 0.0,
            }
        ],
        sample_size=50,
    )

    assert len(rows) == 1
    assert rows[0]["id"] == "e2e-human-001"
    assert "proxy_citation_high_low_format" in rows[0]["tags"]
    assert "cid=c1" in rows[0]["retrieved_evidence"]
    for annotator in ("a1", "a2"):
        for metric in END_TO_END_HUMAN_METRICS:
            assert f"{annotator}_{metric}" in rows[0]
        assert f"{annotator}_unsupported_claim_notes" in rows[0]


def test_aggregate_end_to_end_human_eval_supports_citation_support_metric():
    summary = _aggregate_human_eval(
        [
            {
                "a1_legal_correctness": "4",
                "a2_legal_correctness": "5",
                "a1_grounding": "4",
                "a2_grounding": "4",
                "a1_citation_correctness": "3",
                "a2_citation_correctness": "4",
                "a1_directness": "5",
                "a2_directness": "5",
                "a1_refusal": "5",
                "a2_refusal": "5",
                "a1_citation_support_score": "3",
                "a2_citation_support_score": "4",
            }
        ],
        "end_to_end.tsv",
        metric_names=END_TO_END_HUMAN_METRICS,
        label="End-to-End Human Evaluation",
    )

    assert summary["evaluation_label"] == "End-to-End Human Evaluation"
    assert summary["metrics"]["citation_support_score"]["mean"] == 3.5
    assert summary["score_distribution"]["citation_support_score"]["weak_fail_rate_le3"] == 0.5

def test_generation_baselines_table_excludes_not_distinct_oracle():
    table = _generation_baselines_table(
        {
            "baselines": [
                {"variant": "qwen_prompt_only", "samples": 200, "token_f1": 0.5},
                {"variant": "qwen_qlora", "samples": 200, "token_f1": 0.59},
                {
                    "variant": "oracle_evidence_qwen",
                    "samples": 200,
                    "token_f1": 0.5,
                    "status": "not_distinct",
                    "exclude_from_main_table": True,
                    "diagnostic_note": "not a distinct upper-bound baseline",
                },
            ]
        }
    )

    main_table = table.split("Diagnostic rows excluded", 1)[0]
    assert "qwen_prompt_only" in main_table
    assert "qwen_qlora" in main_table
    assert "oracle_evidence_qwen" not in main_table
    assert "not a distinct upper-bound baseline" in table


def test_human_error_categories_include_weak_citation_correctness():
    human = _categorize_human_errors(
        [
            {
                "question": "q1",
                "a1_citation_correctness": "3",
                "a2_citation_correctness": "3",
                "a1_legal_correctness": "4",
                "a2_legal_correctness": "4",
            }
        ]
    )

    assert human["counts"]["low_human_citation_correctness"] == 1
    assert human["denominator"] == 1


def test_render_human_eval_markdown_includes_distribution_and_disclosure():
    summary = _aggregate_human_eval(
        [
            {
                "a1_legal_correctness": "5",
                "a2_legal_correctness": "3",
                "a1_grounding": "4",
                "a2_grounding": "4",
                "a1_citation_correctness": "3",
                "a2_citation_correctness": "3",
                "a1_directness": "5",
                "a2_directness": "5",
                "a1_refusal": "5",
                "a2_refusal": "5",
            }
        ],
        "annotations.csv",
    )

    markdown = _render_human_eval_markdown(summary)

    assert "2 human annotators scored independently" in markdown
    assert "no AI-assisted scoring" in markdown
    assert "We evaluate 1 examples, each scored by two human annotators" in markdown
    assert "2 annotation scores per metric" in markdown
    assert "preliminary human assessment" in markdown
    assert "not expert legal validation" in markdown
    assert "descriptive statistics, not formal inter-annotator reliability coefficients" in markdown
    assert "Human Evaluation Compact Summary" in markdown
    assert "| Metric | Mean | Std | Exact Agree | Within-1 Agree | Pass >=4 | Weak/Fail <=3 |" in markdown
    assert "legal_correctness | 4.0 | 1.0 | 0.0 | 0.0 | 0.5 | 0.5" in markdown
    assert "Human Evaluation Score Distribution" in markdown
    assert "Weak/Fail Rate <=3" in markdown
    assert "legal_correctness | 2 | 0 | 0 | 1 | 0 | 1 | 0.5 | 0.5" in markdown


def test_paper_draft_uses_english_section_headings_and_safe_claims():
    draft = Path("reports/paper_draft.md").read_text(encoding="utf-8")

    for heading in (
        "## Abstract",
        "## 1. Introduction",
        "## 2. Related Work",
        "## 3. Method",
        "## 4. Experimental Setup",
        "## 5. Results",
        "## 6. Discussion",
        "## 7. Limitations",
        "## 8. Conclusion",
        "## References",
    ):
        assert heading in draft
    for vietnamese_heading in ("Tóm tắt", "Giới thiệu", "Thảo luận", "Hạn chế", "Kết luận", "Tài liệu tham khảo"):
        assert vietnamese_heading not in draft
    for insight in (
        "Evidence ranking remains the main bottleneck.",
        "Cross-encoder reranking substantially improves retrieval.",
        "QLoRA improves answer overlap but not all quality dimensions.",
        "Citation quality requires human evaluation because proxy metrics overestimate it.",
    ):
        assert insight in draft
    for technical_detail in (
        "max_chars=1600",
        "overlap_chars=120",
        "HashingVectorizer",
        "cross-encoder/ms-marco-MiniLM-L-6-v2",
        "rank `16`",
        "alpha `32`",
        "dropout `0.05`",
        "4-bit NF4",
        "maximum sequence length `4096`",
    ):
        assert technical_detail in draft
    assert "A remaining risk is possible semantic overlap below this threshold" in draft
    assert "We ensure that evaluation questions are excluded" not in draft
    assert "citation-aware generation" not in draft
    assert "evidence-aware, citation-oriented generation" in draft
    assert "non-expert Vietnamese speakers" in draft
    assert "without formal legal training" in draft
    assert "Vietnamese QA resources" in draft
    assert "UIT-ViQuAD" in draft
    assert "VLQA" in draft
    assert "VIMQA" not in draft
    for table_heading in (
        "### Dataset Statistics",
        "### Retrieval Ablation",
        "### End-to-End RAG Generation",
        "### Generation Baselines",
        "### Human Evaluation",
    ):
        assert table_heading in draft
    assert "retrieved cross-encoder context | 5 | 200 | 0.5474 | 0.4092" in draft
    assert "oracle/SFT-context QLoRA obtains Token F1 0.5909 and ROUGE-L 0.4808" in draft
    assert "retrieved-context QLoRA with cross-encoder top-5 evidence drops to Token F1 0.5474 and ROUGE-L 0.4092" in draft
    assert "Automatic citation and faithfulness proxies measure surface evidence overlap" in draft
    assert "human-eval item `human-014`" in draft
    assert "automatic proxy citation correctness 1.0 and faithfulness proxy 0.9408" in draft
    assert "smoke validation only" not in draft
    assert "0 exact duplicates, 0 normalized duplicates, and 2 near duplicates" in draft
    assert "cross-encoder/ms-marco-MiniLM-L-6-v2" in draft
    assert "English MS MARCO model" in draft
    assert "BM25-style hashing" not in draft
    assert "character-level dense retrieval" not in draft
    assert "hashing-based sparse lexical retrieval" in draft
    assert "character n-gram hashing retrieval" in draft
    assert "replace raw URLs with BibTeX entries" not in draft
    assert "https://" not in draft
    bib = Path("reports/references.bib").read_text(encoding="utf-8")
    for key in (
        "lewis2020rag",
        "zhang2024raft",
        "guha2023legalbench",
        "hu2021lora",
        "dettmers2023qlora",
        "qwen2024qwen25",
        "nguyen2020uitviquad",
        "nguyen2025vlqa",
    ):
        assert f"@" in bib and key in bib
    assert "VLQA: The First Comprehensive, Large, and High-Quality Vietnamese Dataset for Legal Question Answering" in bib
    assert "Nguyen, Tan-Minh and Nguyen, Hoang-Trung and Dao, Trong-Khoi" in bib
    assert "arXiv preprint arXiv:2507.19995" in bib
    lowered = draft.lower()
    assert "legally reliable" not in lowered
    assert "solves vietnamese legalqa" not in lowered
    assert "automatic proxy citation correctness" in draft
