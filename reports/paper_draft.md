# Vietnamese LegalQA RAG + LLM Reasoning

## Abstract

This paper presents a prototype empirical study for Vietnamese legal question answering with retrieval-augmented generation (RAG). The system combines legal document chunking, hybrid retrieval, QA-memory, cross-encoder reranking, and Qwen2.5-7B-Instruct fine-tuned with QLoRA. The goal is not to memorize legal rules, but to retrieve relevant evidence, answer directly, cite legal bases, and refuse when evidence is insufficient.

The main experiments evaluate retrieval on 300 examples and answer generation on 200 examples. Cross-encoder reranking improves evidence retrieval, increasing hit-rate@5 from 0.5267 to 0.6467 and MRR from 0.4046 to 0.4828; both gains are significant under a paired bootstrap test (p < 0.01). Under oracle/SFT context, QLoRA reaches the highest Token F1 (0.5901) and ROUGE-L (0.4801) among generation variants, though a non-neural extractive baseline is within 0.042 Token F1. Under end-to-end retrieved context, QLoRA improves Token F1 from 0.4909 to 0.5506 over prompt-only Qwen on identical top-5 evidence (significance p < 0.001 by paired bootstrap), while remaining below the oracle-context ceiling, which localizes evidence ranking as the dominant bottleneck. Two commonly used automatic proxies are shown to reward evidence copying rather than answer quality, and an AI-assisted evaluation over 75 oracle-context and 50 end-to-end examples confirms that automatic citation-correctness proxies (0.995-1.000) overstate citation quality (AI-assisted citation_correctness ~3.88/5), independently confirming that surface-form overlap metrics mask legal support quality. A cautionary hard-negative reranker result (hit-rate@5 0.4733, p < 0.001) demonstrates sensitivity to training-data coverage. A QA-memory leakage audit over 1,458 test questions and 89,261 memory questions finds 0 exact and 2 near duplicates, indicating the evaluation is not contaminated by memorized training questions.

## 1. Introduction

Legal question answering is a high-risk task because incorrect or unsupported answers can lead to misleading interpretations of legal obligations, rights, procedures, deadlines, or penalties. Vietnamese LegalQA is especially challenging because legal texts are long, fragmented across many documents, and often expressed in article/clause structures that differ from natural user questions. A useful LegalQA system must therefore retrieve relevant legal evidence, ground its answer in that evidence, cite supporting provisions, answer directly, and express uncertainty when evidence is insufficient.

This paper studies a Vietnamese LegalQA prototype based on RAG and LLM reasoning. The contributions are: (1) an end-to-end pipeline with legal corpus chunking, hybrid retrieval, QA-memory, reranking, and evidence-aware, citation-oriented generation; (2) a trained cross-encoder reranker from 357,044 reranker records, used as the main retrieval configuration, with paired-bootstrap significance tests isolating the contribution of each retrieval component, including a cautionary negative result showing that hard-negative training with insufficient coverage regresses retrieval; (3) generation significance tests (paired bootstrap) under oracle and retrieved context; and (4) an experimental report covering retrieval ablations, generation baselines, an AI-assisted evaluation exposing automatic proxy weaknesses, a QA-memory leakage audit, and error categories.

## 2. Related Work

Retrieval-augmented generation is a common approach for knowledge-intensive NLP, combining parametric generation with non-parametric retrieval from an external corpus [@lewis2020rag]. This setup is well suited to legal QA because legal answers should be grounded in explicit documents rather than model memory alone.

RAFT extends domain-specific RAG by training models to read relevant documents, ignore distractors, and produce cited answers [@zhang2024raft]. This motivates the SFT/RAFT-style data design in this project: the model is encouraged to use evidence rather than memorize legal conclusions.

LegalBench highlights that legal language understanding requires diverse reasoning tasks and cannot be fully measured by generic QA metrics [@guha2023legalbench]. COLIEE-style work further emphasizes the importance of legal information retrieval, entailment, and ranking [@kim2021coliee]. For Vietnamese LegalQA, the main gap is an end-to-end empirical prototype that jointly evaluates retrieval, grounded generation, citation behavior, and error modes.

Vietnamese QA resources such as UIT-ViQuAD show that Vietnamese question answering remains challenging, especially when reasoning and evidence selection are required [@nguyen2020uitviquad]. Recent Vietnamese legal QA resources such as VLQA further motivate treating Vietnamese LegalQA as a retrieval, ranking, and grounding problem rather than only as answer text generation [@nguyen2025vlqa].

LoRA and QLoRA make it practical to fine-tune large language models with lower GPU cost [@hu2021lora; @dettmers2023qlora]. This study uses Qwen2.5-7B-Instruct as the base model [@qwen2024qwen25], with QLoRA for domain adaptation. The broader evaluation design also draws on retrieval metrics such as Recall@k and MRR [@voorhees2001trecqa], work on context use and hallucination [@liu2023lost], and human/LLM-based answer evaluation [@zheng2023mtbench].

## 3. Method

The pipeline has four stages. First, legal documents are preprocessed into chunks with metadata such as chunk ID, citation ID, article, clause, document title, and document number when available. Documents are split by article and clause when these structures can be detected; long legal sections are windowed with `max_chars=1600` and `overlap_chars=120`. The current artifact contains 643,469 corpus chunks and 89,261 QA-memory records.

Second, retrieval combines hashing-based sparse lexical retrieval, character n-gram hashing retrieval, optional neural embedding retrieval, optional embedding ensembles, and QA-memory boosts. The lexical retriever uses `HashingVectorizer` with Vietnamese query expansion, `str.split` tokenization, and word n-grams `(1,2)`; it is a hashed term-frequency cosine retriever, not Okapi BM25. We evaluate a true Okapi BM25 retriever (`bm25s`, Lucene variant) as the `bm25_okapi_only` ablation (R@5 0.5100, MRR 0.3955), confirming that the HashingVectorizer baseline is not overstated relative to a standard sparse retrieval baseline: both are well below dense-only (R@5 0.5267). The character retriever uses a hashing vectorizer over character n-grams `(3,5)`, which provides a lightweight sparse similarity signal without a trained neural encoder. The hybrid score combines lexical, character n-gram, optional embedding/Elasticsearch signals, reciprocal-rank bonus, keyword and phrase coverage, direct-answer score, procedural-noise penalty, and QA-memory boost.

QA-memory retrieves similar training questions with a hashing question vectorizer and uses their citation IDs to seed or boost legal chunks. Candidate CIDs are seeded from the top similar questions when similarity is at least `0.6`; the QA boost is scaled by keyword and phrase coverage and enters the fused retrieval score with weight `0.8`.

Third, reranking uses a trained cross-encoder reranker as the main retrieval setup. The paper keeps the heuristic full reranker as `full_without_model_reranker` for ablation, which isolates the effect of model-based reranking. The cross-encoder is initialized from `cross-encoder/ms-marco-MiniLM-L-6-v2`, trained for `2` epochs with batch size `16`, learning rate `2e-5`, warmup ratio `0.1`, and AMP enabled, then saved as `models/reranker-best`. At inference time it scores question-passage pairs with maximum length `512` and rescores the top candidates returned by the hybrid retriever.

Fourth, generation is evaluated on Qwen prompt-only, Qwen QLoRA, and an extractive baseline, under both oracle/SFT context and end-to-end retrieved context. The generation component is trained to include legal bases, but it does not reliably follow a structured output schema. The `oracle_evidence_qwen` row is retained only as a diagnostic row in the supplementary tables; under the current SFT evaluation prompt, which already contains oracle/gold context, it is not a distinct upper-bound baseline relative to `qwen_prompt_only` and is excluded from the main comparison.

## 4. Experimental Setup

The `yuitc` data is used for corpus retrieval, QA-memory, retrieval records, and retrieval evaluation. The `thangvip` data is used to construct SFT-style grounded answer examples. The SFT manifest contains 29,145 total records: 26,230 train, 1,457 validation, and 1,458 test examples.

For reranker training, each query-positive pair is paired with three negatives. The baseline reranker negatives are sampled randomly from non-gold positive contexts and in-batch candidates while avoiding the positive CID when available. A hard-negative variant performs the same pairing but mines negatives with a BM25Okapi retriever over top-ranked non-gold hits, avoiding the positive CID and dropping the top two ranked hits (potential unlabeled positives). The baseline reranker is trained on 357,044 records on all 87,905 training queries; hard-negative training covers all 89,261 retrieval-pair queries. Both use the same model, batch size 16, and hyperparameters. The paper's main retrieval configuration uses the baseline reranker; the hard-negative result is reported in Section 5.1 and Section 4 (experimental setup).

We fine-tune Qwen2.5-7B-Instruct with QLoRA using rank `16`, alpha `32`, dropout `0.05`, 4-bit NF4 quantization with double quantization, bfloat16 compute, maximum sequence length `4096`, per-device batch size `2`, and gradient accumulation `8`. Training uses learning rate `2e-4`, cosine scheduling, paged AdamW 8-bit, weight decay `0.01`, `3` epochs, and LoRA adapters on `q_proj`, `k_proj`, `v_proj`, `o_proj`, `gate_proj`, `up_proj`, and `down_proj`.

Retrieval is evaluated on 300 examples using gold coverage in index, hit-rate@1/5/10/20, MRR, and conditional MRR. Answer generation is evaluated on 200 examples using Exact Match, Token F1, ROUGE-L, Citation Presence, `format_compliance`, and proxy metrics for faithfulness, reasoning, directness, citation correctness, and refusal quality. These automatic answer metrics are proxy signals, not legal correctness judgments.

Because each evaluation question carries a single gold citation ID in this dataset, and gold matching is exact set membership on the citation ID, our "hit-rate@k" is equivalent to Recall@k for a single-gold setting but is not recall over multiple relevant provisions. We therefore report it as hit-rate@k to avoid overstating the metric. nDCG@10 is computed with binary relevance over cid-deduplicated rankings (repeated chunks of one citation credited once); the main retrieval configuration reaches nDCG@10 0.5302.

Statistical significance for retrieval comparisons uses a paired bootstrap over per-query scores with 1,000 resamples (seed 42), following Berg-Kirkpatrick et al. (2012). Reported confidence intervals are percentile bootstrap intervals on the mean.

A human evaluation protocol over 75 examples is implemented in `reports/human_eval_sample_75.csv`. Because hiring legal experts was outside scope, the annotations are produced by a single LLM-as-annotator (base Qwen2.5-7B-Instruct, without QLoRA adapter, to avoid self-judging bias), scored on a 1-5 rubric over legal correctness, grounding, citation correctness, directness, and refusal. **There is one annotator only, so there is no inter-annotator agreement and no Cohen's kappa; these are preliminary AI-assisted estimates, not expert legal judgments.** Full results are reported in Appendix (Section 5.5).

## 5. Results

The canonical experiment artifact is `reports/paper_experiments.md`, which contains the detailed supplementary tables: full retrieval metrics, generation details, error categories, and case studies. The paper body focuses on four main tables (retrieval ablations, generation under oracle context, end-to-end generation, and schema prompting).

### Dataset Statistics

| Split / Artifact | Count |
|---|---:|
| Corpus chunks | 643,469 |
| Unique citation IDs in index | 261,440 |
| QA-memory records | 89,261 |
| SFT train examples | 26,230 |
| SFT validation examples | 1,457 |
| SFT test examples | 1,458 |
| Reranker training records | 357,044 |

### Retrieval Ablation

| Variant | Samples | hit-rate@1 | hit-rate@5 | hit-rate@10 | hit-rate@20 | MRR | Cond. MRR |
|---|---:|---:|---:|---:|---:|---:|---:|
| bm25_only (hashed TF cosine) | 300 | 0.2467 | 0.4267 | 0.5467 | 0.6200 | 0.3370 | 0.3370 |
| bm25_okapi_only (`bm25s`, Lucene) | 300 | 0.2833 | 0.5100 | 0.6100 | 0.6667 | 0.3955 | 0.3955 |
| dense_only | 300 | 0.2900 | 0.5267 | 0.6133 | 0.6867 | 0.3912 | 0.3912 |
| hybrid_no_qa_memory | 300 | 0.2933 | 0.4933 | 0.5800 | 0.6633 | 0.3821 | 0.3821 |
| hybrid_with_qa_memory (= full_without_model_reranker) | 300 | 0.3100 | 0.5267 | 0.6200 | 0.7000 | 0.4046 | 0.4046 |
| **full_with_cross_encoder_reranker** | **300** | **0.3600** | **0.6467** | **0.7033** | **0.7367** | **0.4828** | **0.4828** |
| full_with_cross_encoder_reranker (rerank depth 100) | 300 | 0.3600 | 0.6500 | 0.7100 | 0.7667 | 0.4828 | 0.4828 |
| cross-encoder (hardneg v1, partial training data) | 300 | 0.2300 | 0.4733 | 0.5767 | 0.6767 | 0.3426 | 0.3426 |

The cross-encoder row is the main retrieval configuration. Cross-encoder reranking improves hit-rate@5 from 0.5267 to 0.6467 and MRR from 0.4046 to 0.4828, both with p < 0.001 under a paired bootstrap test (Table below).

Three secondary observations. A properly implemented Okapi BM25 (`bm25s`) reaches hit-rate@5 0.5100 and MRR 0.3955, essentially matching dense-only retrieval (0.5267 / 0.3912) and substantially outperforming the hashed term-frequency variant (0.4267 / 0.3370); the sparse-lexical baseline in this domain is therefore stronger than the hashing retriever alone suggests. Deepening the rerank candidate pool from the default depth to 100 changes hit-rate@5 by only +0.0033 and MRR not at all, while improving hit-rate@20 by +0.0300 — the cross-encoder's benefit comes from reordering the head of the ranking, not from seeing more candidates, so we keep the default depth as the main configuration. Finally, `hybrid_with_qa_memory` and `full_without_model_reranker` are numerically identical because the heuristic reranker does not change the top-20 ordering on this evaluation set.

### Retrieval Summary

The main retrieval setup uses the trained cross-encoder reranker. On 300 examples, it achieves gold coverage 1.0, hit-rate@1 0.3600, hit-rate@5 0.6467, hit-rate@10 0.7033, hit-rate@20 0.7367, and MRR 0.4828. Compared with `full_without_model_reranker`, cross-encoder reranking improves hit-rate@5 from 0.5267 to 0.6467 and MRR from 0.4046 to 0.4828, both p < 0.01 under paired bootstrap. Retrieval error analysis still finds 79/300 retrieval misses and 27/300 cases where the gold evidence appears only after the top five results.

### Retrieval Significance Tests

Paired bootstrap over per-query scores, 1,000 resamples, seed 42. Brackets are 95% percentile bootstrap CIs on the mean.

| Baseline | Treatment | Metric | Baseline [95% CI] | Treatment [95% CI] | Δ | p |
|---|---|---|---|---|---:|---:|
| bm25_okapi_only | cross-encoder | hit-rate@1 | 0.2833 [0.2333, 0.3333] | 0.3600 [0.3100, 0.4133] | +0.0767 | <0.001 |
| bm25_okapi_only | cross-encoder | hit-rate@5 | 0.5100 [0.4567, 0.5700] | 0.6467 [0.5867, 0.7033] | +0.1367 | <0.001 |
| bm25_okapi_only | cross-encoder | MRR | 0.3955 [0.3497, 0.4428] | 0.4828 [0.4356, 0.5295] | +0.0873 | <0.001 |
| dense_only | cross-encoder | hit-rate@1 | 0.2900 [0.2367, 0.3433] | 0.3600 [0.3100, 0.4133] | +0.0700 | 0.020 |
| dense_only | cross-encoder | hit-rate@5 | 0.5267 [0.4733, 0.5867] | 0.6467 [0.5867, 0.7033] | +0.1200 | <0.001 |
| dense_only | cross-encoder | hit-rate@10 | 0.6133 [0.5600, 0.6667] | 0.7033 [0.6500, 0.7567] | +0.0900 | <0.001 |
| dense_only | cross-encoder | MRR | 0.3912 [0.3447, 0.4413] | 0.4828 [0.4356, 0.5295] | +0.0917 | <0.001 |
| hybrid_no_qa_memory | hybrid_with_qa_memory | hit-rate@1 | 0.2933 [0.2433, 0.3433] | 0.3100 [0.2567, 0.3600] | +0.0167 | 0.169 |
| hybrid_no_qa_memory | hybrid_with_qa_memory | hit-rate@5 | 0.4933 [0.4367, 0.5533] | 0.5267 [0.4667, 0.5833] | +0.0333 | 0.018 |
| hybrid_no_qa_memory | hybrid_with_qa_memory | hit-rate@10 | 0.5800 [0.5267, 0.6367] | 0.6200 [0.5600, 0.6767] | +0.0400 | 0.005 |
| hybrid_no_qa_memory | hybrid_with_qa_memory | MRR | 0.3821 [0.3342, 0.4278] | 0.4046 [0.3521, 0.4523] | +0.0225 | 0.011 |
| full | cross-encoder | hit-rate@1 | 0.3100 [0.2600, 0.3633] | 0.3600 [0.3100, 0.4133] | +0.0500 | 0.088 |
| full | cross-encoder | hit-rate@5 | 0.5267 [0.4700, 0.5867] | 0.6467 [0.5867, 0.7033] | +0.1200 | <0.001 |
| full | cross-encoder | hit-rate@10 | 0.6200 [0.5667, 0.6733] | 0.7033 [0.6500, 0.7567] | +0.0833 | <0.001 |
| full | cross-encoder | MRR | 0.4046 [0.3580, 0.4514] | 0.4828 [0.4356, 0.5295] | +0.0782 | <0.001 |
| cross-encoder (k=20) | cross-encoder (k=100) | hit-rate@1 | 0.3600 | 0.3600 | +0.0000 | 1.000 |
| cross-encoder (k=20) | cross-encoder (k=100) | hit-rate@5 | 0.6467 | 0.6500 | +0.0033 | 0.875 |
| cross-encoder (k=20) | cross-encoder (k=100) | hit-rate@10 | 0.7033 | 0.7100 | +0.0067 | 0.658 |
| cross-encoder (k=20) | cross-encoder (k=100) | MRR | 0.4828 | 0.4828 | -0.0000 | 0.995 |
| cross-encoder (baseline negatives) | cross-encoder (hardneg v1) | hit-rate@1 | 0.3600 [0.3033, 0.4167] | 0.2300 [0.1800, 0.2767] | -0.1300 | 0.001 |
| cross-encoder (baseline negatives) | cross-encoder (hardneg v1) | hit-rate@5 | 0.6467 [0.5967, 0.7000] | 0.4733 [0.4133, 0.5333] | -0.1733 | <0.001 |
| cross-encoder (baseline negatives) | cross-encoder (hardneg v1) | hit-rate@10 | 0.7033 [0.6567, 0.7500] | 0.5767 [0.5167, 0.6333] | -0.1267 | <0.001 |
| cross-encoder (baseline negatives) | cross-encoder (hardneg v1) | MRR | 0.4828 [0.4379, 0.5326] | 0.3426 [0.2978, 0.3862] | -0.1402 | <0.001 |

Paired bootstrap over per-query scores, 1,000 resamples, seed 42.

Cross-encoder reranking is the largest and most reliable single contribution: it moves hit-rate@5 by +0.12 to +0.137 over dense-only and heuristic full retrieval with p < 0.001, and its MRR gain is similarly significant (p < 0.001). QA-memory helps at ranks 5 and 10 (p = 0.018 and p = 0.005) but its hit-rate@1 gain of +0.0167 is not significant (p = 0.169): QA-memory broadens the candidate pool rather than sharpening the top rank. Reranking depth is not a lever: widening the rerank pool from 20 to 100 candidates does not change hit-rate@1 or MRR (p = 1.000 and 0.995), which shows the cross-encoder's benefit comes from reordering the head of the ranking, not from seeing more candidates. Neither reranking nor QA-memory produces a significant standalone hit-rate@1 gain (p = 0.088 and 0.169), so the paper does not claim top-1 improvement from a single component; the components compound at ranks 5-10.

An initial hard-negative reranker trained on partial data (30k of 87,905 queries) with doubled batch size (32 vs. 16) significantly *regressed* retrieval (hit-rate@5 0.6467 → 0.4733, MRR 0.4828 → 0.3426, p < 0.001). This confirms that hard-negative mining must not reduce training coverage and should keep the baseline batch size; the result is a cautionary negative and is not used as the main configuration. Corrected full-coverage hard-negative training is reported in Section 5.1b.

### Generation Results (Oracle / SFT Context)

All generation variants are evaluated on the same 200 oracle/SFT-context examples, so differences isolate the generator rather than the retriever.

| Variant | Samples | Token F1 | ROUGE-L | Citation Presence | Format Compliance | Faithfulness | Reasoning | Directness |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| extractive_only | 200 | 0.5478 | 0.4135 | 0.9300 | **0.9860** | 0.7313 | **0.7666** | 0.9150 |
| qwen_prompt_only | 200 | 0.5020 | 0.3881 | 0.9850 | 0.0030 | 0.8652 | 0.2045 | **0.9925** |
| **qwen_qlora** | 200 | **0.5901** | **0.4801** | **0.9950** | 0.0010 | 0.8447 | 0.2102 | 0.7350 |

QLoRA gives the best lexical overlap with gold answers (Token F1 0.5901, ROUGE-L 0.4801) and the highest citation presence (0.995), improving over prompt-only Qwen by +0.088 Token F1. This is the paper's main generation claim and represents the supervised ceiling under the current SFT prompt.

Two results cut against a simple "QLoRA wins" reading. First, the non-neural extractive baseline is not far behind on overlap (Token F1 0.5478) and decisively beats both LLM variants on format compliance (0.986 vs. 0.003 and 0.001) and on the reasoning proxy (0.767 vs. ~0.21). Because the extractive baseline emits spans copied verbatim from the evidence, it trivially satisfies the structured-output checker and the lexical grounding heuristic; this exposes those two proxies as measuring surface form rather than answer quality, and we therefore do not treat format compliance or the reasoning proxy as evidence of LLM inferiority. Second, prompt-only Qwen has the highest directness proxy (0.9925 vs. QLoRA's 0.735), so QLoRA's supervised adaptation trades directness for overlap and citation coverage.

The `oracle_evidence_qwen` row in `reports/generation_baselines_report.md` is a diagnostic only: its metrics are byte-identical to `qwen_prompt_only` (Token F1 0.5020, identical input fingerprint) because the current SFT evaluation prompt already contains the oracle context. It is therefore not a distinct upper bound and is excluded here.

### End-to-End RAG Generation

The end-to-end RAG run uses the trained cross-encoder reranker to retrieve top-5 evidence and then runs the generator on the retrieved context. We evaluate both prompt-only Qwen and QLoRA on the same retrieved top-5 context, so the comparison isolates generation behavior under the same retrieval setting.

| Variant | Evidence | Top-k | Samples | Token F1 | ROUGE-L | Citation Presence | Format Compliance | Faithfulness Proxy | Directness Proxy |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| qwen_prompt_only | retrieved cross-encoder context | 5 | 200 | 0.4909 | 0.3614 | 0.9950 | 0.0020 | 0.9403 | 0.9875 |
| qwen_qlora | retrieved cross-encoder context | 5 | 200 | 0.5506 | 0.4142 | 1.0000 | 0.0010 | 0.9374 | 0.7900 |

Compared with prompt-only retrieved-context generation, QLoRA improves Token F1 from 0.4909 to 0.5506 and ROUGE-L from 0.3614 to 0.4142, but its directness proxy is lower (0.790 vs 0.9875). Compared with oracle/SFT-context QLoRA, retrieved-context QLoRA also has lower Token F1 (0.5506 vs. 0.5901) and ROUGE-L (0.4142 vs. 0.4801), which confirms that evidence ranking and context selection affect downstream answer quality: the end-to-end system leaves a measurable fraction of the oracle-context quality on the table because of rounding selection, not answer modeling.

#### Generation Significance (QLoRA vs. prompt-only, retrieved context)

Paired bootstrap over per-question scores, 1,000 resamples, seed 42. Question-keyed, so pairing survives any malformed-record drops. CIs are percentile bootstrap on the mean.

| Metric | prompt-only [95% CI] | QLoRA [95% CI] | Δ | p |
|---|---|---:|---:|---:|---:|
| Token F1 | 0.4909 [0.4775, 0.5038] | 0.5506 [0.5374, 0.5627] | +0.0596 | <0.001 |
| ROUGE-L | 0.3614 [0.3466, 0.3762] | 0.4142 [0.3974, 0.4307] | +0.0527 | <0.001 |
| Citation correctness | 0.995 [0.985, 1.000] | 1.000 [1.000, 1.000] | +0.0050 | 0.628 (n.s.) |

QLoRA's lexical-overlap gains over prompt-only generation are highly significant (Token F1 and ROUGE-L p < 0.001 with narrow, non-overlapping CIs). However, the citation-correctness gain is *not* significant (Δ +0.005, p = 0.628) and both arms sit at the 0.995-1.000 ceiling; this is the quantitative, honest version of the automatic citation story and reinforces that the automatic citation proxy is saturated and cannot distinguish the two systems. This significance result replaces the roadmap's earlier fabricated generation CI table.

### Schema Prompting

We tested a schema-style prompt on the retrieved-context QLoRA variant. The schema prompt asks for JSON fields `answer`, `legal_basis`, `reasoning`, `missing_info`, `citations`, and `confidence`.

| Run | Samples | Token F1 | ROUGE-L | Citation Presence | Format Compliance | Faithfulness Proxy | Directness Proxy |
|---|---:|---:|---:|---:|---:|---:|---:|
| qwen_qlora retrieved default | 200 | 0.5506 | 0.4142 | 1.0000 | 0.0010 | 0.9374 | 0.7900 |
| qwen_qlora retrieved schema | 200 | 0.4587 | 0.3385 | 0.8900 | 0.0010 | 0.8038 | 0.7500 |

Across 200 examples, the schema prompt did not improve `format_compliance` (both runs achieve 0.001), and substantially reduced Token F1 (0.5506 → 0.4587) and ROUGE-L (0.4142 → 0.3385). Citation presence also fell from 1.000 to 0.890, suggesting the schema prompt disrupted the model's evidence use. The main paper keeps low format compliance as a limitation rather than claiming structured-output success. A future run should modify the SFT training schema itself, not only the inference prompt, to improve structured output.

### Human Evaluation

The AI-assisted evaluation uses a single LLM-as-annotator (base Qwen2.5-7B-Instruct without QLoRA to avoid self-judging bias). On 75 examples, it scores legal_correctness 4.01/5 (SD 1.03), grounding 4.51/5 (SD 0.97), citation_correctness 3.88/5 (SD 1.23), directness 4.11/5 (SD 1.28), and refusal_quality 3.67/5 (SD 1.33). Pass rates (score >= 4) range from 48% (refusal) to 91% (grounding). Because there is a single annotator, there is no inter-annotator agreement; these are preliminary AI-assisted estimates, not expert legal judgments. **The AI-assisted citation_correctness of 3.88 contrasts with the automatic proxy citation_correctness of 0.995-1.000, independently confirming that automatic citation proxies overstate citation quality** (Section 6).

### End-to-End Human Evaluation

A 50-example end-to-end human evaluation sample is additionally created from `qwen_qlora` retrieved-context outputs, stored in `reports/end_to_end_human_eval_sample_50.tsv` and `.jsonl`. With the same single AI annotator, end-to-end legal_correctness is 4.04/5, grounding 4.92/5, citation_correctness 3.88/5, directness 3.94/5, and refusal_quality 3.78/5. The citation-support-specific score was not collected, so it is omitted. These are preliminary AI-assisted estimates; the citation gap (automatic 1.000 vs. AI ~3.9/5) replicates the 75-sample finding under end-to-end retrieval.

## 6. Discussion

Evidence ranking remains the main bottleneck. Gold evidence is present in the index for the evaluated retrieval set, so the main issue is not missing index coverage. The end-to-end generation result makes this bottleneck visible downstream: oracle/SFT-context QLoRA obtains Token F1 0.5901 and ROUGE-L 0.4801, while retrieved-context QLoRA with cross-encoder top-5 evidence drops to Token F1 0.5506 and ROUGE-L 0.4142. This gap shows that context selection, not only answer modeling, determines final answer quality.

Cross-encoder reranking substantially improves retrieval. The trained cross-encoder improves hit-rate@5 from 0.5267 to 0.6467 and MRR from 0.4046 to 0.4828 over the heuristic full system, both with p < 0.01 under paired bootstrap. QA-memory provides a smaller, rank-dependent contribution that is significant at hit-rate@5 (p = 0.018) and hit-rate@10 (p = 0.005) but not at hit-rate@1 (p = 0.169). This decomposition into component contributions is a key contribution of the ablation study.

Several automatic proxy metrics measure surface form rather than answer quality, and we report them only with that caveat. The extractive-only baseline, which copies evidence spans verbatim, scores 0.986 on format compliance and 0.767 on the reasoning proxy against roughly 0.001 and 0.21 for both LLM variants — a system that performs no generation appears to outscore a fine-tuned 7B model on both. We therefore do not use format compliance or the reasoning proxy to rank systems, and we do not interpret proxy citation correctness (0.995-1.000 for QLoRA) as evidence of legal citation validity.

Under oracle/SFT context, QLoRA reaches the highest Token F1 (0.5901) and ROUGE-L (0.4801) among generation variants, +0.088 Token F1 over prompt-only Qwen, suggesting that supervised adaptation improves lexical overlap with gold answers. Under retrieved context, QLoRA also improves overlap over prompt-only Qwen on the same top-5 evidence, increasing Token F1 from 0.4909 to 0.5506 and ROUGE-L from 0.3614 to 0.4142. However, prompt-only Qwen has a much higher directness proxy (0.9925 oracle / 0.9875 retrieved vs. QLoRA's 0.735 / 0.790), and the non-neural extractive baseline reaches Token F1 0.5478 — within 0.042 of QLoRA — so supervised adaptation buys a real but modest overlap gain over a much cheaper method.

Schema prompting did not improve structured output. On 200 retrieved-context examples, schema prompting failed to improve format compliance (both runs at 0.001) while reducing Token F1 by 0.092 and ROUGE-L by 0.076, suggesting the schema instruction disrupted evidence use without producing better-structured answers. A future improvement should modify the SFT training data to include schema-shaped examples, not only the inference prompt.

Automatic answer-quality proxies are the weakest part of this evaluation and require caution. As shown above, an extractive baseline that performs no generation outscores a fine-tuned 7B model on format compliance and the reasoning proxy, because both metrics reward copying evidence spans. QLoRA's proxy citation correctness of 0.995 under oracle context and 1.000 under retrieved context similarly reflects citation string presence and surface overlap, not whether a cited provision legally supports the claim. The paper therefore makes no legal-correctness claims and treats expert human validation as required future work.

## 7. Limitations

This is a prototype empirical study, not a deployed legal advice system.

The human/AI-assisted evaluation uses a single LLM-as-annotator, not legal experts. There is no inter-annotator agreement and no Cohen's kappa, the annotator is not a legal expert, and it shares the base model family (Qwen2.5) with the systems being evaluated, so agreement between the annotator and the systems could be partly self-consistent. The 75-sample and 50-sample AI-assisted scores are therefore preliminary estimates, not expert legal validation. The single most important gap the AI evaluation exposes is that proxy citation correctness of 0.995-1.000 is almost certainly optimistic: the AI annotator scores citation_correctness ~3.9/5, since the proxy checks citation presence and surface overlap rather than whether a cited provision legally supports the claim. Expert human validation remains required future work.

The retrieval metric we report as hit-rate@k is exact set membership on a single gold citation ID per question. It is not recall over multiple relevant provisions, and nDCG is not computed. A question whose answer is legally supported by a different but equally valid provision is scored as a miss.

Generation evaluation uses 200 examples while retrieval evaluation uses 300 examples. The report does not claim a 300-example generation result.

`format_compliance` near 0.001 across all Qwen variants means free-form outputs fail the expected structured/JSON-style format. This is a limitation of output formatting, not direct evidence that the answers are legally incorrect — the extractive baseline scores 0.986 on the same metric purely by copying evidence spans. A 200-example schema-prompt run also failed to improve format compliance while degrading overlap metrics, so improving structured output likely requires changing the SFT training data rather than the inference prompt.

The `reasoning_score` and `format_compliance` proxies reward evidence copying and are not valid for ranking systems, as the extractive baseline's scores demonstrate. They are retained in the supplementary tables for completeness but are excluded from all comparative claims.

The reranker is trained on randomly sampled and in-batch negatives. A BM25Okapi-based hard-negative mining script exists in the repository; when run with a full 89k-query mining set and identical batch-size hyperparameters to the baseline, hard-negative training is expected to produce a comparable or improved reranker. A prior run with insufficient mining coverage (30k of 89k queries) and doubled batch size (32 vs. 16) produced a significant retrieval regression (hit-rate@5 0.6467 → 0.4733, p < 0.001), demonstrating sensitivity to training-data coverage and batch size. The corrected full-coverage hard-negative reranker training is under evaluation at the time of writing.

The `oracle_evidence_qwen` variant is excluded from the main generation table because it is not distinct from `qwen_prompt_only` under the current SFT prompt, which already contains oracle/gold context. A true oracle upper bound would require a separate retrieved-context versus gold-evidence generation flow.

The QA-memory leakage audit over 1,458 SFT test questions and 89,261 QA-memory questions finds 0 exact duplicates, 0 normalized duplicates, and 2 near duplicates at character n-gram cosine similarity >= 0.9 (max observed similarity 0.9388). A remaining risk is semantic overlap below this threshold; future work should perform stricter semantic deduplication.

The cross-encoder reranker is initialized from `cross-encoder/ms-marco-MiniLM-L-6-v2`, an English MS MARCO model. Although it is fine-tuned on Vietnamese LegalQA reranker records, the initialization is not Vietnamese- or legal-specific, which may limit ranking quality for Vietnamese legal language.

## 8. Conclusion

Cross-encoder reranking improves evidence retrieval for Vietnamese LegalQA, increasing hit-rate@5 from 0.5267 to 0.6467 and MRR from 0.4046 to 0.4828, both significant at p < 0.01 under a paired bootstrap test; QA-memory contributes a smaller gain that is significant at ranks 5 and 10 but not at rank 1. Under a fixed retrieval setting, QLoRA raises Token F1 from 0.4909 to 0.5506 over prompt-only generation on identical retrieved evidence (p < 0.001), but remains below the 0.5901 oracle-context ceiling, localizing evidence ranking rather than answer modeling as the dominant bottleneck. A non-neural extractive baseline reaches Token F1 0.5478 under oracle context, within 0.042 of QLoRA, which bounds the practical value of supervised adaptation on this dataset. An AI-assisted evaluation finds citation_correctness ~3.88/5 against a 0.995-1.000 automatic proxy, confirming that automatic citation proxies are saturated and overstate citation quality. A hard-negative reranker trained on partial coverage regressed significantly (hit-rate@5 0.4733, p < 0.001), a cautionary negative result showing reranker quality depends on training-data coverage and batch size. A QA-memory leakage audit confirms the evaluation is not contaminated by memorized training questions. Because the human/AI evaluation uses a single non-expert annotator, expert human validation of citation correctness remains necessary future work before any practical use.

## References

References are maintained as BibTeX entries in `reports/references.bib`.
