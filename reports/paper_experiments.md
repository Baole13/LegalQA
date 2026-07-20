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
| 300 | 20 | 1.0 | 0.35 | 0.6133 | 0.6633 | 0.7033 | 0.4648 | 0.4648 |

## Retrieval Ablation

| variant | samples | top_k | gold_coverage_in_index | recall@1 | recall@5 | recall@10 | recall@20 | mrr | conditional_mrr |
|---|---|---|---|---|---|---|---|---|---|
| bm25_only | 300 | 20 | 1.0 | 0.25 | 0.45 | 0.5567 | 0.6233 | 0.3421 | 0.3421 |
| hybrid_no_qa_memory | 300 | 20 | 1.0 | 0.2633 | 0.48 | 0.56 | 0.62 | 0.3557 | 0.3557 |
| full_without_model_reranker | 300 | 20 | 1.0 | 0.2933 | 0.51 | 0.5833 | 0.6533 | 0.3859 | 0.3859 |
| full_with_cross_encoder_reranker | 300 | 20 | 1.0 | 0.35 | 0.6133 | 0.6633 | 0.7033 | 0.4648 | 0.4648 |
| full | 300 | 20 | 1.0 | 0.2933 | 0.51 | 0.5833 | 0.6533 | 0.3859 | 0.3859 |
| full_top_k_3 | 300 | 3 | 1.0 | 0.2933 | 0.4267 | 0.4267 | 0.4267 | 0.3522 | 0.3522 |
| full_top_k_5 | 300 | 5 | 1.0 | 0.2933 | 0.51 | 0.51 | 0.51 | 0.3712 | 0.3712 |
| full_top_k_8 | 300 | 8 | 1.0 | 0.2933 | 0.51 | 0.5633 | 0.5633 | 0.3788 | 0.3788 |

## Generation Results

| Field | Value |
|---|---|
| `samples` | 200 |
| `exact_match` | 0.0 |
| `token_f1` | 0.5909 |
| `rouge_l` | 0.4808 |
| `citation_presence` | 0.99 |
| `faithfulness_score` | 0.845 |
| `reasoning_score` | 0.2098 |
| `directness_score` | 0.74 |
| `citation_correctness` | 0.99 |
| `refusal_quality` | 1.0 |
| `avg_prediction_length` | 477.7 |
| `avg_gold_length` | 886.0 |
| `variant` | qwen_qlora |
| `dataset` | data/processed/thangvip_legalqa/test.jsonl |
| `base_model` | Qwen/Qwen2.5-7B-Instruct |
| `adapter` | models/qwen2.5-7b-legalqa-qlora |
| `format_compliance` | 0.001 |

## End-to-End RAG Generation

| variant | evidence_mode | retrieval_variant | retrieval_top_k | samples | token_f1 | rouge_l | citation_presence | format_compliance | faithfulness_score | directness_score | citation_correctness | refusal_quality |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| qwen_qlora | retrieved_context_llm | full_with_cross_encoder_reranker | 5 | 200 | 0.5474 | 0.4092 | 1.0 | 0.002 | 0.9408 | 0.8025 | 1.0 | 1.0 |
| qwen_prompt_only | retrieved_context_llm | full_with_cross_encoder_reranker | 5 | 200 | 0.4896 | 0.3592 | 0.98 | 0.001 | 0.9415 | 0.9825 | 0.98 | 1.0 |

## Schema Prompting Before/After

| run | samples | token_f1 | rouge_l | citation_presence | format_compliance | faithfulness_score | directness_score | citation_correctness |
|---|---|---|---|---|---|---|---|---|
| qwen_qlora retrieved default | 200 | 0.5474 | 0.4092 | 1.0 | 0.002 | 0.9408 | 0.8025 | 1.0 |
| qwen_qlora retrieved schema | 5 | 0.3797 | 0.2538 | 0.8 | 0.0 | 0.8034 | 1.0 | 0.8 |

_Schema prompting has only 5 smoke samples; do not claim format-compliance improvement as a paper-scale result._

## QA-Memory Leakage Audit

| Metric | Value |
|---|---:|
| Eval questions | 1458 |
| QA-memory questions | 89261 |
| Exact duplicates | 0 |
| Normalized duplicates | 0 |
| Near duplicates >= 0.9 | 2 |
| Max similarity | 0.9388 |

## Generation Baselines

| variant | samples | exact_match | token_f1 | rouge_l | citation_presence | format_compliance | faithfulness_score | reasoning_score | directness_score | citation_correctness | refusal_quality |
|---|---|---|---|---|---|---|---|---|---|---|---|
| extractive_only | 200 | 0.0 | 0.5478 | 0.4135 | 0.93 | 0.986 | 0.7313 | 0.7666 | 0.915 | 0.93 | 0.965 |
| qwen_prompt_only | 200 | 0.0 | 0.4994 | 0.3896 | 0.99 | 0.002 | 0.8687 | 0.2052 | 0.995 | 0.99 | 1.0 |
| qwen_qlora | 200 | 0.0 | 0.5909 | 0.4808 | 0.99 | 0.001 | 0.845 | 0.2098 | 0.74 | 0.99 | 1.0 |

Diagnostic rows excluded from the main table:
- `oracle_evidence_qwen`: Current SFT evaluation prompt already contains oracle/gold context, so this row is not a distinct upper-bound baseline relative to qwen_prompt_only.

## Human Evaluation

Source: `reports/human_eval_sample_75.csv`

Disclosure: 2 human annotators scored independently after short calibration (3-5 pilot examples); no AI-assisted scoring is reported as Human Evaluation.

We evaluate 75 examples, each scored by two human annotators, resulting in 150 annotation scores per metric.

The annotators are not legal experts, so the evaluation should be interpreted as preliminary human assessment, not expert legal validation.

Agreement values are descriptive statistics, not formal inter-annotator reliability coefficients.

### Human Evaluation Compact Summary

| Metric | Mean | Std | Exact Agree | Within-1 Agree | Pass >=4 | Weak/Fail <=3 |
|---|---:|---:|---:|---:|---:|---:|
| legal_correctness | 4.5133 | 0.8543 | 0.9067 | 1.0 | 0.88 | 0.12 |
| grounding | 3.92 | 0.7791 | 1.0 | 1.0 | 0.76 | 0.24 |
| citation_correctness | 3.64 | 0.48 | 0.52 | 1.0 | 0.64 | 0.36 |
| directness | 4.4933 | 0.8544 | 0.9467 | 1.0 | 0.8933 | 0.1067 |
| refusal | 4.9467 | 0.2247 | 1.0 | 1.0 | 1.0 | 0.0 |

### Human Evaluation Detailed Agreement

| Metric | N | Mean | Std | Mean Abs Diff | Exact Agree | Within-1 Agree |
|---|---:|---:|---:|---:|---:|---:|
| legal_correctness | 150 | 4.5133 | 0.8543 | 0.0933 | 0.9067 | 1.0 |
| grounding | 150 | 3.92 | 0.7791 | 0.0 | 1.0 | 1.0 |
| citation_correctness | 150 | 3.64 | 0.48 | 0.48 | 0.52 | 1.0 |
| directness | 150 | 4.4933 | 0.8544 | 0.0533 | 0.9467 | 1.0 |
| refusal | 150 | 4.9467 | 0.2247 | 0.0 | 1.0 | 1.0 |

### Human Evaluation Score Distribution

| Metric | N | Score 1 | Score 2 | Score 3 | Score 4 | Score 5 | Pass Rate >=4 | Weak/Fail Rate <=3 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| legal_correctness | 150 | 0 | 9 | 9 | 28 | 104 | 0.88 | 0.12 |
| grounding | 150 | 0 | 8 | 28 | 82 | 32 | 0.76 | 0.24 |
| citation_correctness | 150 | 0 | 0 | 54 | 96 | 0 | 0.64 | 0.36 |
| directness | 150 | 0 | 10 | 6 | 34 | 100 | 0.8933 | 0.1067 |
| refusal | 150 | 0 | 0 | 0 | 8 | 142 | 1.0 | 0.0 |

## End-to-End Human Evaluation

| Field | Value |
|---|---|
| `status` | pending_annotations |
| `evaluation_label` | End-to-End Human Evaluation |
| `samples` | 50 |
| `annotators` | 2 |
| `independent` | True |
| `ai_assisted` | False |
| `calibration` | 3-5 pilot examples |
| `rubric_scale` | 1-5 |
| `metric_names` | ['legal_correctness', 'grounding', 'citation_correctness', 'directness', 'refusal', 'citation_support_score'] |
| `notes` | Fill reports/end_to_end_human_eval_sample_50.tsv or pass --end-to-end-human-eval with completed annotations. |

## Retrieval Error Categories (N=300)

| Category | Count / 300 | Rate | Question | Gold evidence/cids | Retrieved evidence | Prediction/error |
|---|---:|---:|---|---|---|---|
| `low_rank_after_top5` | 27 | 0.09 | Thời hạn nộp hồ sơ khai lệ phí môn bài được quy định như thế nào? | rank None cid=74962: "Điều 10. Thời hạn nộp hồ sơ khai thuế của các khoản thu về đất, lệ phí môn bài, lệ phí trước bạ, tiền cấp quyền và các khoản thu khác theo pháp luật quản l... | rank 1 cid=71612: Khai, nộp lệ phí môn bài Việc khai, nộp lệ phí môn bài được thực hiện theo quy định tại Nghị định số 139/2016/NĐ-CP ngày 04/10/2016 của Chính phủ quy định về lệ phí môn bài, Nghị định số 22/2020/NĐ-C... | low_rank_after_top5 |
| `retrieval_miss` | 89 | 0.2967 | Thời hiệu xử phạt đối với nhà xuất bản thực hiện xuất bản điện tử nhưng không được cơ quan nhà nước xác nhận đăng ký hoạt động là bao lâu? | rank None cid=63171: Điều 5. Thời hiệu xử phạt vi phạm hành chính 1. Thời hiệu xử phạt vi phạm hành chính trong lĩnh vực lao động, bảo hiểm xã hội, người lao động Việt Nam đi là... | rank 1 cid=14932: 2. Phạt tiền từ 30.000.000 đồng đến 50.000.000 đồng đối với một trong các hành vi sau đây: a) Xuất bản, phát hành xuất bản phẩm điện tử kèm ứng dụng kỹ thuật, công nghệ gây mất an toàn, an ninh thông... | retrieval_miss |

## Generation Error Categories (N=200)

| Category | Count / 200 | Rate | Question | Gold evidence/cids | Retrieved evidence | Prediction/error |
|---|---:|---:|---|---|---|---|
| `low_format_compliance` | 200 | 1.0 | Theo Khoản 1 Điều 6 của Luật Hộ tịch, những đối tượng nào có quyền và nghĩa vụ đăng ký hộ tịch? | Tra loi: Theo Khoản 1 Điều 6 của Luật Hộ tịch, các đối tượng có quyền và nghĩa vụ đăng ký hộ tịch bao gồm: Công dân Việt Nam, người không quốc tịch thường trú tại Việt Nam. Quy... |  | Dựa trên Khoản 1 Điều 6 của Luật Hộ tịch, các đối tượng có quyền và nghĩa vụ đăng ký hộ tịch bao gồm: Công dân Việt Nam; người không quốc tịch thường trú tại Việt Nam; và công dân nước ngoài thường trú tại Việt Nam (t... |
| `weak_lexical_match` | 1 | 0.005 | Theo Khoản 1 Điều 57 Luật Hộ tịch, Cơ sở dữ liệu hộ tịch có tính chất là gì? | Tra loi: Theo Khoản 1 Điều 57 Luật Hộ tịch, Cơ sở dữ liệu hộ tịch được xác định là tài sản quốc gia. Điều này nhấn mạnh tầm quan trọng đặc biệt của hệ thống thông tin này đối vớ... |  | Theo Khoản 1 Điều 57 Luật Hộ tịch, Cơ sở dữ liệu hộ tịch được xác định là tài sản quốc gia. |
| `wrong_or_weak_citation_proxy` | 2 | 0.01 | Theo Khoản 1 Điều 53 Luật Hộ tịch, cơ quan nào có thẩm quyền thực hiện đăng ký các việc hộ tịch cho công dân Việt Nam cư trú ở nước ngoài? | Tra loi: Theo Khoản 1 Điều 53 Luật Hộ tịch, Cơ quan đại diện của Việt Nam ở nước ngoài có thẩm quyền thực hiện đăng ký các việc hộ tịch theo quy định tại Điều 3 của Luật này cho... |  | Cơ quan có thẩm quyền thực hiện đăng ký các việc hộ tịch cho công dân Việt Nam cư trú ở nước ngoài là Cơ quan đại diện. |

## Human Evaluation Error Categories (N=75)

| Category | Count / 75 | Rate | Question | Gold evidence/cids | Retrieved evidence | Prediction/error |
|---|---:|---:|---|---|---|---|
| `low_human_citation_correctness` | 9 | 0.12 | Việc Nhà nước có "chính sách, biện pháp đồng bộ" để tạo điều kiện cho cá nhân thực hiện quyền, nghĩa vụ đăng ký hộ tịch theo Khoản 1 Điều 8 Luật Hộ... | Tra loi: Việc Nhà nước có "chính sách, biện pháp đồng bộ" theo Khoản 1 Điều 8 Luật Hộ tịch có ý nghĩa quan trọng trong việc đảm bảo tính toàn diện và hiệu quả của công tác hộ tị... |  | Chính sách, biện pháp đồng bộ được đề cập tại Khoản 1 Điều 8 có ý nghĩa quan trọng trong việc đảm bảo tính hiệu quả và khả thi của công tác đăng ký hộ tịch. Nó thể hiện sự cam kết của Nhà nước không chỉ dừng lại ở việ... |
| `low_human_directness` | 3 | 0.04 | Giả sử một công chức có thẩm quyền đăng ký hộ tịch đã thực hiện việc đăng ký khai sinh cho chính con ruột của mình, đồng thời cung cấp thông tin sa... | Tra loi: Theo Điều 12 của Luật Hộ tịch, công chức này đã vi phạm ít nhất hai hành vi bị nghiêm cấm tại Khoản 1: Điểm h ("Người có thẩm quyền quyết định đăng ký hộ tịch thực hiện... |  | Dựa trên Điều 12 của Luật Hộ tịch, công chức này sẽ phải đối mặt với các hậu quả pháp lý sau: Thứ nhất, hành vi đăng ký khai sinh cho chính con ruột của mình là vi phạm điểm h khoản 1 Điều 12 ("Người có thẩm quyền quy... |
| `low_human_grounding` | 4 | 0.0533 | Một người nộp hồ sơ đầy đủ để đăng ký nhận cha, con vào ngày thứ Hai, ngày 04 tháng 11. Công chức tư pháp - hộ tịch nhận thấy cần phải xác minh. Hỏ... | Tra loi: Theo Khoản 2 Điều 25 của Luật Hộ tịch, thời hạn giải quyết là 03 ngày làm việc kể từ ngày nhận đủ giấy tờ. Nếu cần xác minh, thời hạn được kéo dài thêm không quá 05 ngà... |  | Theo Khoản 2 Điều 25 Luật Hộ tịch, thời hạn ban đầu để công chức tư pháp - hộ tịch xem xét và cấp trích lục là 03 ngày làm việc. Tuy nhiên, trường hợp cần phải xác minh, thời hạn này được kéo dài thêm không quá 05 ngà... |
| `low_human_legal_correctness` | 2 | 0.0267 | Một người nộp hồ sơ đầy đủ để đăng ký nhận cha, con vào ngày thứ Hai, ngày 04 tháng 11. Công chức tư pháp - hộ tịch nhận thấy cần phải xác minh. Hỏ... | Tra loi: Theo Khoản 2 Điều 25 của Luật Hộ tịch, thời hạn giải quyết là 03 ngày làm việc kể từ ngày nhận đủ giấy tờ. Nếu cần xác minh, thời hạn được kéo dài thêm không quá 05 ngà... |  | Theo Khoản 2 Điều 25 Luật Hộ tịch, thời hạn ban đầu để công chức tư pháp - hộ tịch xem xét và cấp trích lục là 03 ngày làm việc. Tuy nhiên, trường hợp cần phải xác minh, thời hạn này được kéo dài thêm không quá 05 ngà... |

## Case Studies

### retrieval_failure

Question: Thời hiệu xử phạt đối với nhà xuất bản thực hiện xuất bản điện tử nhưng không được cơ quan nhà nước xác nhận đăng ký hoạt động là bao lâu?

Gold/target: ['63171']

Gold evidence:
- cid 63171: Điều 5. Thời hiệu xử phạt vi phạm hành chính 1. Thời hiệu xử phạt vi phạm hành chính trong lĩnh vực lao động, bảo hiểm xã hội, người lao động Việt Nam đi làm việc ở nước ngoài theo hợp đồng thực hiện theo quy định tại khoản 1 Điều 6 của Luật Xử lý vi phạm hành chính.

Retrieved evidence:
- rank 1, cid 14932: 2. Phạt tiền từ 30.000.000 đồng đến 50.000.000 đồng đối với một trong các hành vi sau đây: a) Xuất bản, phát hành xuất bản phẩm điện tử kèm ứng dụng kỹ thuật, công nghệ gây mất an toàn, an ninh thông tin đối với phương tiện điện tử; b) Bổ sung thông tin mà người sử dụng xuất bản phẩm điện tử không yêu cầu, trừ các thông tin được phép theo quy định 
- rank 2, cid 14932: 3. Phạt tiền từ 100.000.000 đồng đến 200.000.000 đồng đối với một trong các hành vi sau đây: a) Phát hành trên phương tiện điện tử xuất bản phẩm đã có quyết định đình chỉ phát hành, thu hồi, cấm lưu hành, tiêu hủy đối với từng tên xuất bản phẩm; b) Thực hiện xuất bản điện tử nhưng không được cơ quan nhà nước có thẩm quyền xác nhận đăng ký hoạt động
- rank 3, cid 106701: Vi phạm quy định về điều kiện hoạt động xuất bản điện tử và phát hành xuất bản phẩm điện tử ... 3. Phạt tiền từ 100.000.000 đồng đến 200.000.000 đồng đối với một trong các hành vi sau đây: a) Phát hành trên phương tiện điện tử xuất bản phẩm đã có quyết định đình chỉ phát hành, thu hồi, cấm lưu hành, tiêu hủy đối với từng tên xuất bản phẩm; b) Thực 

Signals: `{"hit_rank": null, "gold_in_index": true}`

### generation_or_citation_failure

Question: Theo Khoản 1 Điều 53 Luật Hộ tịch, cơ quan nào có thẩm quyền thực hiện đăng ký các việc hộ tịch cho công dân Việt Nam cư trú ở nước ngoài?

Gold/target: Tra loi: Theo Khoản 1 Điều 53 Luật Hộ tịch, Cơ quan đại diện của Việt Nam ở nước ngoài có thẩm quyền thực hiện đăng ký các việc hộ tịch theo quy định tại Điều 3 của Luật này cho công dân Việt Nam cư trú ở nước ngoài.
Can cu: Luật Hộ tịch của Quốc hội, số 60/2014/QH13 - Dieu 53.
Lap luan: Evidence duoc cung cap khop voi noi dung cau hoi; do do cau tra loi chi rut ra tu dieu/khoan nay va khong suy doan ngoai van ban.
Thong tin con thieu: Khong co them thong tin can bo sung neu chi dua tren evidence hien co.

Gold evidence:

Retrieved evidence:

Prediction: Cơ quan có thẩm quyền thực hiện đăng ký các việc hộ tịch cho công dân Việt Nam cư trú ở nước ngoài là Cơ quan đại diện.

Signals: `{"hit_rank": null, "faithfulness_score": 0.75, "citation_presence": 0.0, "citation_correctness": 0.0, "directness_score": 1.0}`

## Notes

- Faithfulness, reasoning, directness, citation correctness, and refusal quality are proxy metrics.
- Human evaluation uses two human annotators who scored independently after a short 3-5 example calibration; no AI-assisted scoring is reported as human evaluation.
- The hybrid_no_qa_memory ablation disables QA-memory seeding/boosting during retrieval evaluation only.
- Top-k ablation rows cap the number of retrieved evidence chunks available to downstream generation.
- The main retrieval table uses the trained cross-encoder reranker when the full_with_cross_encoder_reranker row is available; heuristic full retrieval is reported as an ablation.
- Format compliance measures adherence to the expected structured output format, not legal correctness; low values are treated as a formatting limitation.
- oracle_evidence_qwen is diagnostic only: the current SFT prompt already contains oracle/gold context, so it is not a distinct upper-bound baseline.
- Answer generation report contains 200 samples, not the 300-sample retrieval run; do not claim it as the main 300-sample generation result.
- Schema prompting report contains only 5 samples; treat it as smoke validation and do not claim schema prompting improves format compliance.
