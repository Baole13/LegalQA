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

| samples | top_k | gold_coverage_in_index | recall@1 | recall@5 | recall@10 | recall@20 | mrr | ndcg@10 | conditional_mrr |
|---|---|---|---|---|---|---|---|---|---|
| 300 | 20 | 1.0 | 0.36 | 0.6467 | 0.7033 | 0.7367 | 0.4828 | 0.5302 | 0.4828 |

## Retrieval Ablation

| variant | samples | top_k | gold_coverage_in_index | recall@1 | recall@5 | recall@10 | recall@20 | mrr | ndcg@10 | conditional_mrr |
|---|---|---|---|---|---|---|---|---|---|---|
| bm25_only | 300 | 20 | 1.0 | 0.2467 | 0.4267 | 0.5467 | 0.62 | 0.337 | 0.3816 | 0.337 |
| bm25_okapi_only | 300 | 20 | 1.0 | 0.2833 | 0.51 | 0.61 | 0.6667 | 0.3955 | 0.4368 | 0.3955 |
| dense_only | 300 | 20 | 1.0 | 0.29 | 0.5267 | 0.6133 | 0.6867 | 0.3912 | 0.4377 | 0.3912 |
| hybrid_no_qa_memory | 300 | 20 | 1.0 | 0.2933 | 0.4933 | 0.58 | 0.6633 | 0.3821 | 0.4167 | 0.3821 |
| hybrid_with_qa_memory | 300 | 20 | 1.0 | 0.31 | 0.5267 | 0.62 | 0.7 | 0.4046 | 0.4463 | 0.4046 |
| full_without_model_reranker | 300 | 20 | 1.0 | 0.31 | 0.5267 | 0.62 | 0.7 | 0.4046 | 0.4463 | 0.4046 |
| full_with_cross_encoder_reranker | 300 | 20 | 1.0 | 0.36 | 0.6467 | 0.7033 | 0.7367 | 0.4828 | 0.5302 | 0.4828 |
| full_with_cross_encoder_reranker_k100 | 300 | 20 | 1.0 | 0.36 | 0.65 | 0.71 | 0.7667 | 0.4828 | 0.5313 | 0.4828 |
| full_with_cross_encoder_reranker_hardneg | 300 | 20 | 1.0 | 0.23 | 0.4733 | 0.5767 | 0.6767 | 0.3426 | 0.3873 | 0.3426 |
| full | 300 | 20 | 1.0 | 0.31 | 0.5267 | 0.62 | 0.7 | 0.4046 | 0.4463 | 0.4046 |
| full_top_k_3 | 300 | 3 | 1.0 | 0.31 | 0.45 | 0.45 | 0.45 | 0.3689 | 0.381 | 0.3689 |
| full_top_k_5 | 300 | 5 | 1.0 | 0.31 | 0.5267 | 0.5267 | 0.5267 | 0.3867 | 0.4132 | 0.3867 |
| full_top_k_8 | 300 | 8 | 1.0 | 0.31 | 0.5267 | 0.59 | 0.59 | 0.3959 | 0.4343 | 0.3959 |

- **BM25 (hashing):** lexical retrieval with a hashed word 1-2 gram vector space and cosine scoring; this is the lexical channel used inside the hybrid fuser, not textbook BM25.
- **BM25 (Okapi):** true Okapi BM25 (Lucene variant, k1=1.5, b=0.75) over the same chunk corpus, reported as the standard lexical baseline.
- **Dense:** semantic retrieval using neural embeddings and a normalized FAISS cosine index.
- **Hybrid:** combines lexical, dense, and ranking signals to balance exact matches with semantic recall.
- **Hybrid + QA-memory:** uses similar questions to seed and boost related legal-document candidates.
- **Cross-encoder reranker:** directly scores each question-passage pair from Hybrid + QA-memory candidates to improve final ranking; `_k100` widens the candidate pool from 50 to 100.
- **nDCG@10:** binary-relevance nDCG over cid-deduplicated rankings, so repeated chunks of one citation are credited once.

## Generation Results

| Field | Value |
|---|---|
| `samples` | 200 |
| `exact_match` | 0.0 |
| `token_f1` | 0.5901 |
| `rouge_l` | 0.4801 |
| `citation_presence` | 0.995 |
| `format_compliance` | 0.001 |
| `faithfulness_score` | 0.8447 |
| `reasoning_score` | 0.2102 |
| `directness_score` | 0.735 |
| `citation_correctness` | 0.995 |
| `refusal_quality` | 1.0 |
| `avg_prediction_length` | 479.12 |
| `avg_gold_length` | 886.0 |
| `variant` | qwen_qlora |
| `dataset` | data/processed/thangvip_legalqa/test.jsonl |
| `base_model` | Qwen/Qwen2.5-7B-Instruct |
| `adapter` | models/qwen2.5-7b-legalqa-qlora |
| `evidence_mode` | sft_prompt_context |
| `baseline_note` | Base Qwen plus LegalQA QLoRA adapter. |
| `prompt_style` | default |
| `input_fingerprint` | f6714feadeef14e8c7d5d039641482a655279bf89fdc2a5d0ebbf6795465b8b7 |

## End-to-End RAG Generation

| variant | evidence_mode | retrieval_variant | retrieval_top_k | samples | token_f1 | rouge_l | citation_presence | format_compliance | faithfulness_score | directness_score | citation_correctness | refusal_quality |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| qwen_qlora | retrieved_context_llm | full_with_cross_encoder_reranker | 5 | 200 | 0.5506 | 0.4142 | 1.0 | 0.001 | 0.9374 | 0.79 | 1.0 | 1.0 |
| qwen_prompt_only | retrieved_context_llm | full_with_cross_encoder_reranker | 5 | 200 | 0.4909 | 0.3614 | 0.995 | 0.002 | 0.9403 | 0.9875 | 0.995 | 1.0 |

## Schema Prompting Before/After

| run | samples | token_f1 | rouge_l | citation_presence | format_compliance | faithfulness_score | directness_score | citation_correctness |
|---|---|---|---|---|---|---|---|---|
| qwen_qlora retrieved default | 200 | 0.5506 | 0.4142 | 1.0 | 0.001 | 0.9374 | 0.79 | 1.0 |
| qwen_qlora retrieved schema | 200 | 0.4587 | 0.3385 | 0.89 | 0.001 | 0.8038 | 0.75 | 0.89 |

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
| qwen_prompt_only | 200 | 0.0 | 0.502 | 0.3881 | 0.985 | 0.003 | 0.8652 | 0.2045 | 0.9925 | 0.985 | 1.0 |
| qwen_qlora | 200 | 0.0 | 0.5901 | 0.4801 | 0.995 | 0.001 | 0.8447 | 0.2102 | 0.735 | 0.995 | 1.0 |

Diagnostic rows excluded from the main table:
- `oracle_evidence_qwen`: Current SFT evaluation prompt already contains oracle/gold context, so this row is not a distinct upper-bound baseline relative to qwen_prompt_only.

## Human Evaluation

Source: `reports/human_eval_sample_75.csv`

Disclosure: 1 annotator(s) scored not independently after short calibration (LLM-as-annotator single pass); AI-assisted scoring disclosed is reported as Human Evaluation.

We evaluate 75 examples, each scored by 1 annotator(s), resulting in 75 annotation scores per metric.

The annotators are not legal experts, so the evaluation should be interpreted as preliminary human assessment, not expert legal validation.

Agreement values are descriptive statistics, not formal inter-annotator reliability coefficients.

### Human Evaluation Compact Summary

| Metric | Mean | Std | Exact Agree | Within-1 Agree | Pass >=4 | Weak/Fail <=3 |
|---|---:|---:|---:|---:|---:|---:|
| legal_correctness | 4.0133 | 1.0262 | None | None | 0.7067 | 0.2933 |
| grounding | 4.5067 | 0.9712 | None | None | 0.9067 | 0.0933 |
| citation_correctness | 3.88 | 1.2325 | None | None | 0.6933 | 0.3067 |
| directness | 4.1067 | 1.2814 | None | None | 0.6933 | 0.3067 |
| refusal | 3.6667 | 1.33 | None | None | 0.48 | 0.52 |

### Human Evaluation Detailed Agreement

| Metric | N | Mean | Std | Mean Abs Diff | Exact Agree | Within-1 Agree |
|---|---:|---:|---:|---:|---:|---:|
| legal_correctness | 75 | 4.0133 | 1.0262 | None | None | None |
| grounding | 75 | 4.5067 | 0.9712 | None | None | None |
| citation_correctness | 75 | 3.88 | 1.2325 | None | None | None |
| directness | 75 | 4.1067 | 1.2814 | None | None | None |
| refusal | 75 | 3.6667 | 1.33 | None | None | None |

### Human Evaluation Score Distribution

| Metric | N | Score 1 | Score 2 | Score 3 | Score 4 | Score 5 | Pass Rate >=4 | Weak/Fail Rate <=3 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| legal_correctness | 75 | 3 | 1 | 18 | 23 | 30 | 0.7067 | 0.2933 |
| grounding | 75 | 3 | 2 | 2 | 15 | 53 | 0.9067 | 0.0933 |
| citation_correctness | 75 | 5 | 7 | 11 | 21 | 31 | 0.6933 | 0.3067 |
| directness | 75 | 3 | 10 | 10 | 5 | 47 | 0.6933 | 0.3067 |
| refusal | 75 | 8 | 2 | 29 | 4 | 32 | 0.48 | 0.52 |

## End-to-End Human Evaluation

Source: `reports/end_to_end_human_eval_sample_50.tsv`

Disclosure: 1 annotator(s) scored not independently after short calibration (LLM-as-annotator single pass); AI-assisted scoring disclosed is reported as End-to-End Human Evaluation.

We evaluate 50 examples, each scored by 1 annotator(s), resulting in 50 annotation scores per metric.

The annotators are not legal experts, so the evaluation should be interpreted as preliminary human assessment, not expert legal validation.

Agreement values are descriptive statistics, not formal inter-annotator reliability coefficients.

### Human Evaluation Compact Summary

| Metric | Mean | Std | Exact Agree | Within-1 Agree | Pass >=4 | Weak/Fail <=3 |
|---|---:|---:|---:|---:|---:|---:|
| legal_correctness | 4.04 | 0.6621 | None | None | 0.8 | 0.2 |
| grounding | 4.92 | 0.2713 | None | None | 1.0 | 0.0 |
| citation_correctness | 3.88 | 0.84 | None | None | 0.7 | 0.3 |
| directness | 3.94 | 0.9468 | None | None | 0.7 | 0.3 |
| refusal | 3.78 | 1.4871 | None | None | 0.56 | 0.44 |
| citation_support_score | None | None | None | None | 0.0 | 0.0 |

### Human Evaluation Detailed Agreement

| Metric | N | Mean | Std | Mean Abs Diff | Exact Agree | Within-1 Agree |
|---|---:|---:|---:|---:|---:|---:|
| legal_correctness | 50 | 4.04 | 0.6621 | None | None | None |
| grounding | 50 | 4.92 | 0.2713 | None | None | None |
| citation_correctness | 50 | 3.88 | 0.84 | None | None | None |
| directness | 50 | 3.94 | 0.9468 | None | None | None |
| refusal | 50 | 3.78 | 1.4871 | None | None | None |
| citation_support_score | 0 | None | None | None | None | None |

### Human Evaluation Score Distribution

| Metric | N | Score 1 | Score 2 | Score 3 | Score 4 | Score 5 | Pass Rate >=4 | Weak/Fail Rate <=3 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| legal_correctness | 50 | 0 | 0 | 10 | 28 | 12 | 0.8 | 0.2 |
| grounding | 50 | 0 | 0 | 0 | 4 | 46 | 1.0 | 0.0 |
| citation_correctness | 50 | 0 | 3 | 12 | 23 | 12 | 0.7 | 0.3 |
| directness | 50 | 1 | 2 | 12 | 19 | 16 | 0.7 | 0.3 |
| refusal | 50 | 6 | 5 | 11 | 0 | 28 | 0.56 | 0.44 |
| citation_support_score | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0.0 |

## Retrieval Error Categories (N=300)

| Category | Count / 300 | Rate | Question | Gold evidence/cids | Retrieved evidence | Prediction/error |
|---|---:|---:|---|---|---|---|
| `low_rank_after_top5` | 27 | 0.09 | Người học ngành điện công nghiệp trình độ cao đẳng sau khi tốt nghiệp có thể làm những công việc nào? | rank None cid=73585: Vị trí việc làm sau khi tốt nghiệp Sau khi tốt nghiệp người học có năng lực đáp ứng các yêu cầu tại các vị trí việc làm của ngành, nghề bao gồm: - Lắp đặt h... | rank 1 cid=160975: Vị trí việc làm sau khi tốt nghiệp Sau khi tốt nghiệp chương trình đào tạo trung cấp, người học có thể đảm nhiệm các vị trí công việc: - Biểu diễn nhạc cổ điển thính phòng; - Biểu diễn nhạc Pop/Rock... | low_rank_after_top5 |
| `retrieval_miss` | 79 | 0.2633 | Thời hiệu xử phạt đối với nhà xuất bản thực hiện xuất bản điện tử nhưng không được cơ quan nhà nước xác nhận đăng ký hoạt động là bao lâu? | rank None cid=63171: Điều 5. Thời hiệu xử phạt vi phạm hành chính 1. Thời hiệu xử phạt vi phạm hành chính trong lĩnh vực lao động, bảo hiểm xã hội, người lao động Việt Nam đi là... | rank 1 cid=106701: Vi phạm quy định về điều kiện hoạt động xuất bản điện tử và phát hành xuất bản phẩm điện tử ... 3. Phạt tiền từ 100.000.000 đồng đến 200.000.000 đồng đối với một trong các hành vi sau đây: a) Phát h... | retrieval_miss |

## Generation Error Categories (N=200)

| Category | Count / 200 | Rate | Question | Gold evidence/cids | Retrieved evidence | Prediction/error |
|---|---:|---:|---|---|---|---|
| `low_format_compliance` | 200 | 1.0 | Theo Khoản 1 Điều 6 của Luật Hộ tịch, những đối tượng nào có quyền và nghĩa vụ đăng ký hộ tịch? | Tra loi: Theo Khoản 1 Điều 6 của Luật Hộ tịch, các đối tượng có quyền và nghĩa vụ đăng ký hộ tịch bao gồm: Công dân Việt Nam, người không quốc tịch thường trú tại Việt Nam. Quy... |  | Theo Khoản 1 Điều 6 của Luật Hộ tịch, các đối tượng có quyền và nghĩa vụ đăng ký hộ tịch bao gồm: Công dân Việt Nam, người không quốc tịch thường trú tại Việt Nam. Ngoài ra, quy định này cũng được áp dụng đối với công... |
| `weak_lexical_match` | 1 | 0.005 | Theo Khoản 1 Điều 57 Luật Hộ tịch, Cơ sở dữ liệu hộ tịch có tính chất là gì? | Tra loi: Theo Khoản 1 Điều 57 Luật Hộ tịch, Cơ sở dữ liệu hộ tịch được xác định là tài sản quốc gia. Điều này nhấn mạnh tầm quan trọng đặc biệt của hệ thống thông tin này đối vớ... |  | Theo Khoản 1 Điều 57 Luật Hộ tịch, Cơ sở dữ liệu hộ tịch được xác định là tài sản quốc gia. |
| `wrong_or_weak_citation_proxy` | 1 | 0.005 | Theo Khoản 1 Điều 60, những thông tin nào của cá nhân phải được cập nhật vào Cơ sở dữ liệu hộ tịch điện tử? | Tra loi: Theo Khoản 1 Điều 60 của Luật Hộ tịch, các sự kiện hộ tịch của cá nhân ngay sau khi đăng ký vào Sổ hộ tịch đều phải được cập nhật kịp thời, đầy đủ, chính xác vào Cơ sở... |  | Các sự kiện hộ tịch của cá nhân ngay sau khi được đăng ký vào Sổ hộ tịch đều phải được cập nhật kịp thời, đầy đủ và chính xác vào Cơ sở dữ liệu hộ tịch điện tử. |

## Human Evaluation Error Categories (N=75)

| Category | Count / 75 | Rate | Question | Gold evidence/cids | Retrieved evidence | Prediction/error |
|---|---:|---:|---|---|---|---|
| `low_human_citation_correctness` | 23 | 0.3067 | Ai có thẩm quyền quyết định thành lập Hội đồng tư vấn cấp Chứng chỉ hành nghề dược Sở Y tế? | cid=62339 Thành lập Hội đồng 1. Bộ trưởng Bộ Y tế ra quyết định thành lập Hội đồng tư vấn cấp Chứng chỉ hành nghề dược theo hình thức thi (sau đây gọi tắt là Hội đồng tư vấn cấp... |  | low_human_citation_correctness |
| `low_human_directness` | 13 | 0.1733 | Trình tự, thủ tục nhượng bán tài sản của Ngân hàng Chính sách xã hội như thế nào? | cid=64246 Thanh lý, nhượng bán tài sản cố định ... 4. Trình tự, thủ tục thanh lý, nhượng bán tài sản: a) Chủ tịch Hội đồng thành viên hoặc Chủ tịch công ty quyết định thành lập... |  | low_human_directness |
| `low_human_grounding` | 5 | 0.0667 | Giáo viên nhận tiền để sửa điểm thi có thể bị truy cứu trách nhiệm tội nhận hối lộ hay không? | cid=62232 Điều 353. Tội tham ô tài sản 1. Người nào lợi dụng chức vụ, quyền hạn chiếm đoạt tài sản mà mình có trách nhiệm quản lý trị giá từ 2.000.000 đồng đến dưới 100.000.000... |  | low_human_grounding |
| `low_human_legal_correctness` | 4 | 0.0533 | Bệnh giảm áp nghề nghiệp được chẩn đoán lâm sàng sẽ có những triệu chứng nào? | cid=153320 Chẩn đoán 7.1. Lâm sàng 7.1.1. Bệnh giảm áp a) Cấp tính - Mức độ nhẹ: Là hình thành bóng khí dưới da (tràn khí dưới da), tràn khí màng phổi, trung thất hoặc xương, kh... |  | low_human_legal_correctness |
| `low_human_refusal` | 10 | 0.1333 | Người chứng kiến có phải giữ bí mật hoạt động điều tra mà mình chứng kiến không? | cid=61582 “4. Người chứng kiến có nghĩa vụ: [… ] d) Giữ bí mật về hoạt động điều tra mà mình chứng kiến; […]” |  | low_human_refusal |

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

### generation_or_citation_failure

Question: Theo Khoản 1 Điều 60, những thông tin nào của cá nhân phải được cập nhật vào Cơ sở dữ liệu hộ tịch điện tử?

Gold/target: Tra loi: Theo Khoản 1 Điều 60 của Luật Hộ tịch, các sự kiện hộ tịch của cá nhân ngay sau khi đăng ký vào Sổ hộ tịch đều phải được cập nhật kịp thời, đầy đủ, chính xác vào Cơ sở dữ liệu hộ tịch điện tử.
Can cu: Luật Hộ tịch của Quốc hội, số 60/2014/QH13 - Dieu 60.
Lap luan: Evidence duoc cung cap khop voi noi dung cau hoi; do do cau tra loi chi rut ra tu dieu/khoan nay va khong suy doan ngoai van ban.
Thong tin con thieu: Khong co them thong tin can bo sung neu chi dua tren evidence hien co.

Gold evidence:

Retrieved evidence:

Prediction: Các sự kiện hộ tịch của cá nhân ngay sau khi được đăng ký vào Sổ hộ tịch đều phải được cập nhật kịp thời, đầy đủ và chính xác vào Cơ sở dữ liệu hộ tịch điện tử.

Signals: `{"hit_rank": null, "faithfulness_score": 0.7308, "citation_presence": 0.0, "citation_correctness": 0.0, "directness_score": 1.0}`

## Notes

- Faithfulness, reasoning, directness, citation correctness, and refusal quality are proxy metrics.
- Human evaluation uses a single LLM-as-annotator pass (AI-assisted scoring), so there is no inter-annotator agreement and no Cohen's kappa; it is a preliminary assessment, not expert legal validation.
- The hybrid_no_qa_memory ablation disables QA-memory seeding/boosting during retrieval evaluation only.
- Top-k ablation rows cap the number of retrieved evidence chunks available to downstream generation.
- The main retrieval table uses the trained cross-encoder reranker when the full_with_cross_encoder_reranker row is available; heuristic full retrieval is reported as an ablation.
- Format compliance measures adherence to the expected structured output format, not legal correctness; low values are treated as a formatting limitation.
- oracle_evidence_qwen is diagnostic only: the current SFT prompt already contains oracle/gold context, so it is not a distinct upper-bound baseline.
- Answer generation report contains 200 samples, not the 300-sample retrieval run; do not claim it as the main 300-sample generation result.
