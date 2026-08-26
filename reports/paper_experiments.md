# Paper Experiments Report

All grounding-oriented answer metrics in this report are proxy metrics, not legal-expert judgments.

## Dataset Statistics

| Field | Value |
|---|---|
| `corpus_chunks` | 643469 |
| `qa_memory_records` | 89261 |
| `index_created_at` | 2026-05-16T09:33:28.558616+00:00 |
| `sft_total_records` | 29145 |
| `sft_train_records` | 26230 |
| `sft_val_records` | 1457 |
| `sft_test_records` | 1458 |
| `retriever_records` | 89261 |
| `reranker_records` | 357044 |
| `negatives_per_query` | 3 |
| `base_model` | Qwen/Qwen2.5-7B-Instruct |
| `qlora_train_records` | 26230 |
| `qlora_eval_records` | 500 |

## Retrieval Results

| samples | top_k | gold_coverage_in_index | recall@1 | recall@5 | recall@10 | recall@20 | mrr | conditional_mrr |
|---|---|---|---|---|---|---|---|---|
| 300 | 20 | 1.0 | 0.36 | 0.6467 | 0.7033 | 0.7367 | 0.4828 | 0.4828 |

## Retrieval Ablation

| variant | samples | top_k | gold_coverage_in_index | recall@1 | recall@5 | recall@10 | recall@20 | mrr | conditional_mrr |
|---|---|---|---|---|---|---|---|---|---|
| bm25_only | 300 | 20 | 1.0 | 0.2467 | 0.4267 | 0.5467 | 0.62 | 0.337 | 0.337 |
| dense_only | 300 | 20 | 1.0 | 0.29 | 0.5267 | 0.6133 | 0.6867 | 0.3912 | 0.3912 |
| hybrid_no_qa_memory | 300 | 20 | 1.0 | 0.2933 | 0.4933 | 0.58 | 0.6633 | 0.3821 | 0.3821 |
| hybrid_with_qa_memory | 300 | 20 | 1.0 | 0.31 | 0.5267 | 0.62 | 0.7 | 0.4046 | 0.4046 |
| full_without_model_reranker | 300 | 20 | 1.0 | 0.31 | 0.5267 | 0.62 | 0.7 | 0.4046 | 0.4046 |
| full_with_cross_encoder_reranker | 300 | 20 | 1.0 | 0.36 | 0.6467 | 0.7033 | 0.7367 | 0.4828 | 0.4828 |
| full | 300 | 20 | 1.0 | 0.31 | 0.5267 | 0.62 | 0.7 | 0.4046 | 0.4046 |
| full_top_k_3 | 300 | 3 | 1.0 | 0.31 | 0.45 | 0.45 | 0.45 | 0.3689 | 0.3689 |
| full_top_k_5 | 300 | 5 | 1.0 | 0.31 | 0.5267 | 0.5267 | 0.5267 | 0.3867 | 0.3867 |
| full_top_k_8 | 300 | 8 | 1.0 | 0.31 | 0.5267 | 0.59 | 0.59 | 0.3959 | 0.3959 |

- **BM25:** lexical retrieval based on matching words and phrases.
- **Dense:** semantic retrieval using neural embeddings and a normalized FAISS cosine index.
- **Hybrid:** combines lexical, dense, and ranking signals to balance exact matches with semantic recall.
- **Hybrid + QA-memory:** uses similar questions to seed and boost related legal-document candidates.
- **Cross-encoder reranker:** directly scores each question-passage pair from Hybrid + QA-memory candidates to improve final ranking.

## Generation Results

| Field | Value |
|---|---|
| `samples` | 0 |

## End-to-End RAG Generation

| variant | evidence_mode | retrieval_variant | retrieval_top_k | samples | token_f1 | rouge_l | citation_presence | format_compliance | faithfulness_score | directness_score | citation_correctness | refusal_quality |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
|  |  |  |  | 0 |  |  |  |  |  |  |  |  |
|  |  |  |  | 0 |  |  |  |  |  |  |  |  |

## Schema Prompting Before/After

| run | samples | token_f1 | rouge_l | citation_presence | format_compliance | faithfulness_score | directness_score | citation_correctness |
|---|---|---|---|---|---|---|---|---|
| qwen_qlora retrieved default | 0 |  |  |  |  |  |  |  |
| qwen_qlora retrieved schema | 0 |  |  |  |  |  |  |  |

_Schema prompting has only 0 smoke samples; do not claim format-compliance improvement as a paper-scale result._

## QA-Memory Leakage Audit

_No QA-memory leakage audit found. Run `PYTHONPATH=. python scripts/audit_qa_memory_leakage.py --eval-dataset data/processed/thangvip_legalqa/test.jsonl --near-threshold 0.9`._

## Generation Baselines

_No generation baselines report found. Run `scripts/eval_answer_generation.py --variant all_baselines` to populate this table._

## Human Evaluation

| Field | Value |
|---|---|
| `status` | pending_annotations |
| `evaluation_label` | Human Evaluation |
| `samples` | 75 |
| `annotators` | 2 |
| `independent` | True |
| `ai_assisted` | False |
| `calibration` | 3-5 pilot examples |
| `rubric_scale` | 1-5 |
| `metrics` | ['legal_correctness', 'grounding', 'citation_correctness', 'directness', 'refusal'] |
| `notes` | Fill reports/human_eval_sample_75.csv or pass --human-eval with completed annotations. |

## End-to-End Human Evaluation

| Field | Value |
|---|---|
| `status` | pending_annotations |
| `evaluation_label` | End-to-End Human Evaluation |
| `samples` | 0 |
| `annotators` | 2 |
| `independent` | True |
| `ai_assisted` | False |
| `calibration` | 3-5 pilot examples |
| `rubric_scale` | 1-5 |
| `metric_names` | ['legal_correctness', 'grounding', 'citation_correctness', 'directness', 'refusal', 'citation_support_score'] |
| `notes` | Fill reports/end_to_end_human_eval_sample_0.tsv or pass --end-to-end-human-eval with completed annotations. |

## Retrieval Error Categories (N=300)

| Category | Count / 300 | Rate | Question | Gold evidence/cids | Retrieved evidence | Prediction/error |
|---|---:|---:|---|---|---|---|
| `low_rank_after_top5` | 27 | 0.09 | Người học ngành điện công nghiệp trình độ cao đẳng sau khi tốt nghiệp có thể làm những công việc nào? | rank None cid=73585: Vị trí việc làm sau khi tốt nghiệp Sau khi tốt nghiệp người học có năng lực đáp ứng các yêu cầu tại các vị trí việc làm của ngành, nghề bao gồm: - Lắp đặt h... | rank 1 cid=160975: Vị trí việc làm sau khi tốt nghiệp Sau khi tốt nghiệp chương trình đào tạo trung cấp, người học có thể đảm nhiệm các vị trí công việc: - Biểu diễn nhạc cổ điển thính phòng; - Biểu diễn nhạc Pop/Rock... | low_rank_after_top5 |
| `retrieval_miss` | 79 | 0.2633 | Thời hiệu xử phạt đối với nhà xuất bản thực hiện xuất bản điện tử nhưng không được cơ quan nhà nước xác nhận đăng ký hoạt động là bao lâu? | rank None cid=63171: Điều 5. Thời hiệu xử phạt vi phạm hành chính 1. Thời hiệu xử phạt vi phạm hành chính trong lĩnh vực lao động, bảo hiểm xã hội, người lao động Việt Nam đi là... | rank 1 cid=106701: Vi phạm quy định về điều kiện hoạt động xuất bản điện tử và phát hành xuất bản phẩm điện tử ... 3. Phạt tiền từ 100.000.000 đồng đến 200.000.000 đồng đối với một trong các hành vi sau đây: a) Phát h... | retrieval_miss |

## Generation Error Categories (N=0)

_No error categories found._

## Human Evaluation Error Categories (N=0)

_No error categories found._

## Case Studies

### retrieval_failure

Question: Thời hiệu xử phạt đối với nhà xuất bản thực hiện xuất bản điện tử nhưng không được cơ quan nhà nước xác nhận đăng ký hoạt động là bao lâu?

Gold/target: ['63171']

Gold evidence:
- cid 63171: Điều 5. Thời hiệu xử phạt vi phạm hành chính 1. Thời hiệu xử phạt vi phạm hành chính trong lĩnh vực lao động, bảo hiểm xã hội, người lao động Việt Nam đi làm việc ở nước ngoài theo hợp đồng thực hiện theo quy định tại khoản 1 Điều 6 của Luật Xử lý vi phạm hành chính.

Retrieved evidence:
- rank 1, cid 106701: Vi phạm quy định về điều kiện hoạt động xuất bản điện tử và phát hành xuất bản phẩm điện tử ... 3. Phạt tiền từ 100.000.000 đồng đến 200.000.000 đồng đối với một trong các hành vi sau đây: a) Phát hành trên phương tiện điện tử xuất bản phẩm đã có quyết định đình chỉ phát hành, thu hồi, cấm lưu hành, tiêu hủy đối với từng tên xuất bản phẩm; b) Thực 
- rank 2, cid 106701: Vi phạm quy định về điều kiện hoạt động xuất bản điện tử và phát hành xuất bản phẩm điện tử ... 3. Phạt tiền từ 100.000.000 đồng đến 200.000.000 đồng đối với một trong các hành vi sau đây: a) Phát hành trên phương tiện điện tử xuất bản phẩm đã có quyết định đình chỉ phát hành, thu hồi, cấm lưu hành, tiêu hủy đối với từng tên xuất bản phẩm; b) Thực 
- rank 3, cid 106701: Vi phạm quy định về điều kiện hoạt động xuất bản điện tử và phát hành xuất bản phẩm điện tử ... 3. Phạt tiền từ 100.000.000 đồng đến 200.000.000 đồng đối với một trong các hành vi sau đây: a) Phát hành trên phương tiện điện tử xuất bản phẩm đã có quyết định đình chỉ phát hành, thu hồi, cấm lưu hành, tiêu hủy đối với từng tên xuất bản phẩm; b) Thực 

Signals: `{"hit_rank": null, "gold_in_index": true}`

## Notes

- Faithfulness, reasoning, directness, citation correctness, and refusal quality are proxy metrics.
- Human evaluation uses two human annotators who scored independently after a short 3-5 example calibration; no AI-assisted scoring is reported as human evaluation.
- The hybrid_no_qa_memory ablation disables QA-memory seeding/boosting during retrieval evaluation only.
- Top-k ablation rows cap the number of retrieved evidence chunks available to downstream generation.
- The main retrieval table uses the trained cross-encoder reranker when the full_with_cross_encoder_reranker row is available; heuristic full retrieval is reported as an ablation.
- Format compliance measures adherence to the expected structured output format, not legal correctness; low values are treated as a formatting limitation.
- Schema prompting report contains only 0 samples; treat it as smoke validation and do not claim schema prompting improves format compliance.
