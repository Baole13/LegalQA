# Vietnamese LegalQA RAG + LLM Reasoning

## Abstract

This paper presents a prototype empirical study for Vietnamese legal question answering with retrieval-augmented generation (RAG). The system combines legal document chunking, hybrid retrieval, QA-memory, cross-encoder reranking, and Qwen2.5-7B-Instruct fine-tuned with QLoRA. The goal is not to memorize legal rules, but to retrieve relevant evidence, answer directly, cite legal bases, and refuse when evidence is insufficient.

The main experiments evaluate retrieval on 300 examples, answer generation on 200 examples, and preliminary human assessment on 75 examples. Cross-encoder reranking improves evidence retrieval, increasing Recall@5 from 0.5100 to 0.6133 and MRR from 0.3859 to 0.4648. QLoRA achieves the highest Token F1 and ROUGE-L among generation baselines, but does not dominate all proxy metrics. Human evaluation shows that citation correctness is the weakest dimension (mean 3.64/5; weak/fail rate 0.36), suggesting that citation validation remains an open challenge. Because the annotators are not legal experts, this evaluation should be interpreted as preliminary human assessment, not expert legal validation.

## 1. Introduction

Legal question answering is a high-risk task because incorrect or unsupported answers can lead to misleading interpretations of legal obligations, rights, procedures, deadlines, or penalties. Vietnamese LegalQA is especially challenging because legal texts are long, fragmented across many documents, and often expressed in article/clause structures that differ from natural user questions. A useful LegalQA system must therefore retrieve relevant legal evidence, ground its answer in that evidence, cite supporting provisions, answer directly, and express uncertainty when evidence is insufficient.

This paper studies a Vietnamese LegalQA prototype based on RAG and LLM reasoning. The contributions are: (1) an end-to-end pipeline with legal corpus chunking, hybrid retrieval, QA-memory, reranking, and evidence-aware, citation-oriented generation; (2) a trained cross-encoder reranker from 357,044 reranker records, used as the main retrieval configuration; and (3) an experimental report covering retrieval, generation baselines, preliminary human assessment, error categories, and case studies.

## 2. Related Work

Retrieval-augmented generation is a common approach for knowledge-intensive NLP, combining parametric generation with non-parametric retrieval from an external corpus [@lewis2020rag]. This setup is well suited to legal QA because legal answers should be grounded in explicit documents rather than model memory alone.

RAFT extends domain-specific RAG by training models to read relevant documents, ignore distractors, and produce cited answers [@zhang2024raft]. This motivates the SFT/RAFT-style data design in this project: the model is encouraged to use evidence rather than memorize legal conclusions.

LegalBench highlights that legal language understanding requires diverse reasoning tasks and cannot be fully measured by generic QA metrics [@guha2023legalbench]. COLIEE-style work further emphasizes the importance of legal information retrieval, entailment, and ranking [@kim2021coliee]. For Vietnamese LegalQA, the main gap is an end-to-end empirical prototype that jointly evaluates retrieval, grounded generation, citation behavior, and error modes.

Vietnamese QA resources such as UIT-ViQuAD show that Vietnamese question answering remains challenging, especially when reasoning and evidence selection are required [@nguyen2020uitviquad]. Recent Vietnamese legal QA resources such as VLQA further motivate treating Vietnamese LegalQA as a retrieval, ranking, and grounding problem rather than only as answer text generation [@nguyen2025vlqa].

LoRA and QLoRA make it practical to fine-tune large language models with lower GPU cost [@hu2021lora; @dettmers2023qlora]. This study uses Qwen2.5-7B-Instruct as the base model [@qwen2024qwen25], with QLoRA for domain adaptation. The broader evaluation design also draws on retrieval metrics such as Recall@k and MRR [@voorhees2001trecqa], work on context use and hallucination [@liu2023lost], and human/LLM-based answer evaluation [@zheng2023mtbench].

## 3. Method

The pipeline has four stages. First, legal documents are preprocessed into chunks with metadata such as chunk ID, citation ID, article, clause, document title, and document number when available. Documents are split by article and clause when these structures can be detected; long legal sections are windowed with `max_chars=1600` and `overlap_chars=120`. The current artifact contains 643,469 corpus chunks and 89,261 QA-memory records.

Second, retrieval combines hashing-based sparse lexical retrieval, character n-gram hashing retrieval, optional neural embedding retrieval, optional embedding ensembles, and QA-memory boosts. The lexical retriever uses `HashingVectorizer` with Vietnamese query expansion, `str.split` tokenization, and word n-grams `(1,2)`. The character retriever uses a hashing vectorizer over character n-grams `(3,5)`, which provides a lightweight sparse similarity signal without a trained neural encoder. The hybrid score combines lexical, character n-gram, optional embedding/Elasticsearch signals, reciprocal-rank bonus, keyword and phrase coverage, direct-answer score, procedural-noise penalty, and QA-memory boost.

QA-memory retrieves similar training questions with a hashing question vectorizer and uses their citation IDs to seed or boost legal chunks. Candidate CIDs are seeded from the top similar questions when similarity is at least `0.6`; the QA boost is scaled by keyword and phrase coverage and enters the fused retrieval score with weight `0.8`.

Third, reranking uses a trained cross-encoder reranker as the main retrieval setup. The paper keeps the heuristic full reranker as `full_without_model_reranker` for ablation, which isolates the effect of model-based reranking. The cross-encoder is initialized from `cross-encoder/ms-marco-MiniLM-L-6-v2`, trained for `2` epochs with batch size `16`, learning rate `2e-5`, warmup ratio `0.1`, and AMP enabled, then saved as `models/reranker-best`. At inference time it scores question-passage pairs with maximum length `512` and rescores the top candidates returned by the hybrid retriever.

Fourth, generation is evaluated with extractive-only, Qwen prompt-only, and Qwen QLoRA variants. The generation component is trained to include legal bases, but it does not reliably follow a structured output schema. The `oracle_evidence_qwen` row is retained only as a diagnostic row because the current SFT evaluation prompt already contains oracle/gold context; it is not a distinct upper-bound baseline relative to `qwen_prompt_only`.

## 4. Experimental Setup

The `yuitc` data is used for corpus retrieval, QA-memory, retrieval records, and retrieval evaluation. The `thangvip` data is used to construct SFT-style grounded answer examples. The SFT manifest contains 29,145 total records: 26,230 train, 1,457 validation, and 1,458 test examples.

For reranker training, each query-positive pair is paired with three negatives. Negatives are sampled from non-gold positive contexts or retrieval candidates while avoiding the positive CID when available. The reranker is trained on 357,044 records and used to rescore the top candidates returned by the hybrid retriever.

We fine-tune Qwen2.5-7B-Instruct with QLoRA using rank `16`, alpha `32`, dropout `0.05`, 4-bit NF4 quantization with double quantization, bfloat16 compute, maximum sequence length `4096`, per-device batch size `2`, and gradient accumulation `8`. Training uses learning rate `2e-4`, cosine scheduling, paged AdamW 8-bit, weight decay `0.01`, `3` epochs, and LoRA adapters on `q_proj`, `k_proj`, `v_proj`, `o_proj`, `gate_proj`, `up_proj`, and `down_proj`.

Retrieval is evaluated on 300 examples using gold coverage in index, Recall@1/5/10/20, MRR, and conditional MRR. Answer generation is evaluated on 200 examples using Exact Match, Token F1, ROUGE-L, Citation Presence, `format_compliance`, and proxy metrics for faithfulness, reasoning, directness, citation correctness, and refusal quality. These automatic answer metrics are proxy signals, not legal correctness judgments.

Human evaluation uses 75 examples. We evaluate 75 examples, each scored by two human annotators, resulting in 150 annotation scores per metric. The annotators scored independently after a short 3-5 example calibration, and no AI-assisted scoring is reported as human evaluation. The annotators are non-expert Vietnamese speakers familiar with the annotation rubric, without formal legal training, so the evaluation should be interpreted as preliminary human assessment, not expert legal validation. Agreement values are descriptive statistics, not formal inter-annotator reliability coefficients.

## 5. Results

The canonical experiment artifact is `reports/paper_experiments.md`, which contains the detailed supplementary tables: full retrieval metrics, generation details, human score distribution, error categories, and case studies. The paper body focuses on five main tables.

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

| Variant | Samples | Recall@1 | Recall@5 | Recall@10 | Recall@20 | MRR | Conditional MRR |
|---|---:|---:|---:|---:|---:|---:|---:|
| bm25_only | 300 | 0.2500 | 0.4500 | 0.5567 | 0.6233 | 0.3421 | 0.3421 |
| hybrid_no_qa_memory | 300 | 0.2633 | 0.4800 | 0.5600 | 0.6200 | 0.3557 | 0.3557 |
| full_without_model_reranker | 300 | 0.2933 | 0.5100 | 0.5833 | 0.6533 | 0.3859 | 0.3859 |
| full_with_cross_encoder_reranker | 300 | 0.3500 | 0.6133 | 0.6633 | 0.7033 | 0.4648 | 0.4648 |

The cross-encoder row is the main retrieval configuration. It improves Recall@5 from 0.5100 to 0.6133 and MRR from 0.3859 to 0.4648.

### Retrieval Summary

The main retrieval setup uses the trained cross-encoder reranker. On 300 examples, it achieves gold coverage 1.0, Recall@1 0.3500, Recall@5 0.6133, Recall@10 0.6633, Recall@20 0.7033, and MRR 0.4648. Compared with `full_without_model_reranker`, cross-encoder reranking improves Recall@5 from 0.5100 to 0.6133 and MRR from 0.3859 to 0.4648. Retrieval error analysis still finds 89/300 retrieval misses and 27/300 cases where the gold evidence appears only after the top five results.

### Generation Results

The oracle/SFT-context QLoRA generation run uses 200 examples and obtains Token F1 0.5909, ROUGE-L 0.4808, Citation Presence 0.99, Faithfulness proxy 0.845, and Directness proxy 0.74. Among generation baselines, QLoRA achieves the highest Token F1 and ROUGE-L: extractive-only obtains Token F1 0.5478, Qwen prompt-only obtains 0.4994, and QLoRA obtains 0.5909. However, Qwen prompt-only has higher directness proxy than QLoRA (0.995 vs. 0.74), so QLoRA should not be interpreted as dominating all quality dimensions.

### End-to-End RAG Generation

The end-to-end RAG run uses the trained cross-encoder reranker to retrieve top-5 evidence and then runs the generator on the retrieved context. We evaluate both prompt-only Qwen and QLoRA on the same retrieved top-5 context, so the comparison isolates generation behavior under the same retrieval setting.

| Variant | Evidence | Top-k | Samples | Token F1 | ROUGE-L | Citation Presence | Format Compliance | Faithfulness Proxy | Directness Proxy |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| qwen_prompt_only | retrieved cross-encoder context | 5 | 200 | 0.4896 | 0.3592 | 0.9800 | 0.0010 | 0.9415 | 0.9825 |
| qwen_qlora | retrieved cross-encoder context | 5 | 200 | 0.5474 | 0.4092 | 1.0000 | 0.0020 | 0.9408 | 0.8025 |

Compared with prompt-only retrieved-context generation, QLoRA improves Token F1 from 0.4896 to 0.5474 and ROUGE-L from 0.3592 to 0.4092, but its directness proxy is lower. Compared with oracle/SFT-context QLoRA, retrieved-context QLoRA also has lower Token F1 and ROUGE-L, which confirms that evidence ranking and context selection affect downstream answer quality.

### Schema Prompting

We also tested a schema-style prompt on a 5-example smoke run for retrieved-context QLoRA. The schema prompt asks for JSON fields `answer`, `legal_basis`, `reasoning`, `missing_info`, `citations`, and `confidence`.

| Run | Samples | Token F1 | ROUGE-L | Citation Presence | Format Compliance | Faithfulness Proxy | Directness Proxy |
|---|---:|---:|---:|---:|---:|---:|---:|
| qwen_qlora retrieved default | 200 | 0.5474 | 0.4092 | 1.0000 | 0.0020 | 0.9408 | 0.8025 |
| qwen_qlora retrieved schema | 5 | 0.3797 | 0.2538 | 0.8000 | 0.0000 | 0.8034 | 1.0000 |

The schema run is only a smoke result and is not used as a paper-scale claim. It did not improve `format_compliance`, so the main paper keeps low format compliance as a limitation rather than claiming structured-output success.

### Generation Baselines

| Variant | Evidence | Samples | Token F1 | ROUGE-L | Citation Presence | Format Compliance | Directness Proxy |
|---|---|---:|---:|---:|---:|---:|---:|
| extractive_only | oracle/SFT context | 200 | 0.5478 | 0.4135 | 0.9300 | 0.9860 | 0.9150 |
| qwen_prompt_only | oracle/SFT context | 200 | 0.4994 | 0.3896 | 0.9900 | 0.0020 | 0.9950 |
| qwen_qlora | oracle/SFT context | 200 | 0.5909 | 0.4808 | 0.9900 | 0.0010 | 0.7400 |

The `oracle_evidence_qwen` diagnostic row is excluded from the main table because it is not distinct from `qwen_prompt_only` under the current SFT prompt.

### Human Evaluation

The compact human evaluation summary is:

| Metric | Mean | Std | Exact Agree | Within-1 Agree | Pass >=4 | Weak/Fail <=3 |
|---|---:|---:|---:|---:|---:|---:|
| Legal correctness | 4.51 | 0.85 | 0.91 | 1.00 | 0.88 | 0.12 |
| Grounding | 3.92 | 0.78 | 1.00 | 1.00 | 0.76 | 0.24 |
| Citation correctness | 3.64 | 0.48 | 0.52 | 1.00 | 0.64 | 0.36 |
| Directness | 4.49 | 0.85 | 0.95 | 1.00 | 0.8933 | 0.1067 |
| Refusal | 4.95 | 0.22 | 1.00 | 1.00 | 1.00 | 0.00 |

Citation correctness is the weakest dimension by both mean score and weak/fail rate. This contrasts with the automatic proxy citation correctness of 0.99, indicating that automatic citation proxies overestimate citation quality.

### End-to-End Human Evaluation

Because the 75-example human evaluation was created before the retrieved-context generation run, we additionally create a 50-example end-to-end human evaluation sample from `qwen_qlora` retrieved-context outputs. The sample is stored in `reports/end_to_end_human_eval_sample_50.tsv` and `reports/end_to_end_human_eval_sample_50.jsonl`. It includes the same five rubric dimensions plus a citation-support-specific score and unsupported-claim notes. These annotations are pending, so the paper does not report end-to-end human scores yet.

## 6. Discussion

Evidence ranking remains the main bottleneck. Gold evidence is present in the index for the evaluated retrieval set, so the main issue is not missing index coverage. The end-to-end generation result makes this bottleneck visible downstream: oracle/SFT-context QLoRA obtains Token F1 0.5909 and ROUGE-L 0.4808, while retrieved-context QLoRA with cross-encoder top-5 evidence drops to Token F1 0.5474 and ROUGE-L 0.4092. This gap shows that context selection, not only answer modeling, determines final answer quality.

Cross-encoder reranking substantially improves retrieval. The trained cross-encoder improves Recall@5 from 0.5100 to 0.6133 and MRR from 0.3859 to 0.4648 over the heuristic full reranker. The retrieved-context generation run is therefore a stronger end-to-end RAG setting than heuristic retrieval alone, even though generation metrics still trail oracle/SFT-context generation. This supports treating cross-encoder reranking as the main retrieval setup and using heuristic retrieval as an ablation.

QLoRA improves answer overlap but not all quality dimensions. Under oracle/SFT context, QLoRA reaches the highest Token F1 and ROUGE-L among generation baselines, suggesting that supervised adaptation improves lexical overlap with gold answers. Under retrieved context, QLoRA also improves overlap over prompt-only Qwen on the same top-5 evidence, increasing Token F1 from 0.4896 to 0.5474 and ROUGE-L from 0.3592 to 0.4092. However, Qwen prompt-only has higher directness proxy, and QLoRA has very low `format_compliance`, so QLoRA should not be interpreted as dominating all quality dimensions.

Citation quality requires human evaluation because proxy metrics overestimate it. Automatic citation and faithfulness proxies measure surface evidence overlap, citation presence, and lexical grounding signals; they do not verify whether a cited provision legally supports the specific claim. This is why retrieved-context QLoRA can receive automatic proxy citation correctness 1.0 and faithfulness proxy 0.9408, while preliminary human assessment still finds citation correctness to be the weakest dimension, with mean 3.64/5 and weak/fail rate 0.36. For example, in human-eval item `human-014`, the answer to a question about Khoản 1 Điều 8 Luật Hộ tịch is plausible but expands to administrative resources and infrastructure not directly stated in the gold evidence, has no citation list, and receives citation correctness 3/5. This kind of error is easy for surface proxies to under-penalize but important for legal QA.

## 7. Limitations

This is a prototype empirical study, not a deployed legal advice system. The human evaluation uses 75 examples and two non-expert annotators; therefore, it should be interpreted as preliminary human assessment rather than expert legal validation. Agreement values are descriptive statistics, not formal inter-annotator reliability coefficients such as weighted kappa.

Generation evaluation uses 200 examples for both oracle/SFT-context QLoRA and retrieved-context QLoRA, while retrieval evaluation uses 300 examples. The report therefore does not claim a 300-example generation result.

`format_compliance = 0.001` for oracle/SFT-context QLoRA and `0.0020` for retrieved-context QLoRA mean that free-form outputs fail the expected structured/JSON-style format. This is a limitation of output formatting, not direct evidence that the answers are legally incorrect. The paper does not claim structured-output success. A 5-example schema-prompt smoke run also failed to improve format compliance, so a future run should modify the prompt or SFT schema more substantially, rerun 200 generation examples, and report before/after format compliance.

The `oracle_evidence_qwen` variant is excluded from the main generation baseline table because it is not distinct from `qwen_prompt_only` under the current SFT prompt, which already contains oracle/gold context. A true oracle upper bound would require a separate retrieved-context versus gold-evidence generation flow.

The QA-memory leakage audit over 1,458 SFT test questions and 89,261 QA-memory questions finds 0 exact duplicates, 0 normalized duplicates, and 2 near duplicates at character n-gram cosine similarity >= 0.9. A remaining risk is possible semantic overlap below this threshold; future work should perform stricter semantic deduplication to rule out leakage.

The cross-encoder reranker is initialized from `cross-encoder/ms-marco-MiniLM-L-6-v2`, an English MS MARCO model. Although it is fine-tuned on Vietnamese LegalQA reranker records, the initialization is not Vietnamese- or legal-specific, which may limit ranking quality for Vietnamese legal language.

## 8. Conclusion

Cross-encoder reranking improves evidence retrieval for Vietnamese LegalQA, increasing Recall@5 from 0.5100 to 0.6133 and MRR from 0.3859 to 0.4648. QLoRA achieves the highest Token F1 and ROUGE-L among generation baselines, but does not dominate all proxy metrics. Preliminary human assessment shows that citation correctness is the weakest evaluated dimension, suggesting that citation validation remains an open challenge for Vietnamese LegalQA.

## References

References are maintained as BibTeX entries in `reports/references.bib`.
