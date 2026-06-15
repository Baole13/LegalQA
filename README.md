# Vietnamese LegalQA Prototype: RAG + LLM Reasoning

Prototype nghiên cứu bài toán LegalQA tiếng Việt theo hướng **RAG truy xuất căn cứ pháp lý** kết hợp **LLM reasoning/fine-tune**. Mục tiêu của repo là xây môi trường thực nghiệm để phân tích retrieval, reranking, QA-memory, prompt-only LLM, SFT và RAFT trong bài toán hỏi đáp pháp luật.
  
## Trạng thái hiện tại

Prototype hiện đã chạy được end-to-end:

- UI hỏi đáp pháp lý qua FastAPI + static frontend.
- RAG pipeline với hybrid retrieval, QA-memory, heuristic reranker và citation/evidence debug.
- LLM reasoning bằng Qwen2.5-7B-Instruct qua Transformers.
- UI/API bật `force_llm_reasoning=true` để ưu tiên LLM đọc evidence và lập luận.
- Có cơ chế `forced_raw` để dùng câu trả lời LLM khi model trả prose thay vì JSON hợp lệ.
- Đã chuẩn bị dữ liệu SFT từ `thangvip` và retrieval/reranker records từ `yuitc`.
- Đã có adapter QLoRA Qwen2.5-7B ở mức prototype.

Những phần **chưa hoàn tất**:

- Chưa hoàn thiện RAFT dataset lớn từ `yuitc`.
- Chưa train/xác nhận cross-encoder reranker thật; hiện serving vẫn dùng heuristic reranker.
- Chưa có benchmark retrieval đầy đủ Recall@k/MRR trên toàn bộ tập test.
- Chưa có human evaluation 100-200 câu để kết luận độ chính xác pháp lý.
- Fine-tune đã chạy ở mức prototype/SFT, nhưng chưa thể kết luận mô hình đã reasoning ổn định trên diện rộng.

## Kiến trúc tổng quan

Pipeline chính gồm 4 tầng:

1. **Retrieval**
   - Hybrid retrieval gồm BM25, char dense, local embedding và QA-memory boost.
   - Corpus hiện tại có khoảng `643,469` chunks.
   - QA-memory hiện có khoảng `89,261` records.

2. **Reranking**
   - Hiện dùng heuristic reranker trong serving.
   - Repo đã có dữ liệu train reranker, nhưng cross-encoder reranker thật chưa phải kết quả serving chính.

3. **Answer generation**
   - Output chuẩn hóa gồm:
     - `answer`
     - `legal_basis`
     - `reasoning`
     - `missing_info`
     - `confidence`
     - `citations`, `quotes`, `evidence`, `retrieval` để debug

4. **LLM reasoning**
   - Dùng Qwen2.5-7B-Instruct.
   - LLM chỉ nên trả lời dựa trên evidence được truy xuất.
   - Fine-tune không nhằm học thuộc luật, mà nhằm học cách đọc evidence, suy luận ngắn, cite nguồn và từ chối khi evidence thiếu.

## Cấu trúc thư mục

```text
configs/
  datasets/              # Config đường dẫn dữ liệu thangvip/yuitc
  research/              # Cấu hình ablation nghiên cứu
  serving/               # Config runtime: retriever, LLM, serving
  training/              # Config train QLoRA, retriever, reranker, RAFT

data/
  raw/                   # Dữ liệu gốc parquet
  processed/             # Chunks, QA-memory, SFT thangvip
  aligned/               # Retriever/reranker/RAFT records
  indexes/               # Artifact index retrieval

frontend/                # Giao diện hỏi đáp
reports/                 # Báo cáo metric 
scripts/                 # Entrypoint chuẩn bị dữ liệu, train, eval, reindex
src/
  api/                   # FastAPI app và schema
  data/                  # Loader và data preparation
  evaluation/            # Answer/retrieval evaluation
  indexing/              # Build/load artifacts
  preprocessing/         # Chunking, metadata, clean text
  qa/                    # Pipeline hỏi đáp, generator, prompt, LLM reasoner
  reranker/              # Heuristic/model reranker
  retrieval/             # BM25/dense/hybrid retriever
  training/              # Qwen SFT, RAFT builders
  utils/                 # Logger, IO, text utilities

tests/                   # Test suite
models/                  # Retriever và LoRA adapters
```

## Dữ liệu

Đặt dữ liệu gốc tại:

```text
data/raw/thangvip/train.parquet
data/raw/yuitc/train.parquet
data/raw/yuitc/test.parquet
```

Vai trò từng dataset:

- `thangvip`: nguồn chính cho SFT reasoning style.
- `yuitc`: nguồn chính cho corpus retrieval, QA-memory, retriever/reranker training, retrieval evaluation và RAFT grounding.

Dữ liệu đã chuẩn bị trong trạng thái hiện tại:

```text
thangvip SFT total: 29,145
- train: 26,230
- val:   1,457
- test:  1,458

yuitc retrieval records: 89,261
yuitc reranker records:  357,044
corpus chunks:           643,469
QA-memory records:       89,261
```

## Cài đặt môi trường

Trên RunPod hoặc môi trường GPU tương tự:

```bash
cd /workspace/baolq
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-runpod.txt
```

Nếu đã có `.venv` sẵn:

```bash
cd /workspace/baolq
source .venv/bin/activate
```

## Chạy demo UI/API

Chạy backend ở port `8000`:

```bash
cd /workspace/baolq
source .venv/bin/activate
uvicorn src.api.app:app --host 127.0.0.1 --port 8000
```

Chờ log:

```text
Application startup complete.
Uvicorn running on http://127.0.0.1:8000
```


```text
public port 8001 -> localhost:8000
```

Ví dụ URL dạng:

```text
https://<pod-id>-8001.proxy.runpod.net
```

Kiểm tra health:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8001/health
```

Nếu gặp lỗi `address already in use`, nghĩa là server đang chạy sẵn. Kiểm tra PID:

```bash
ss -ltnp 'sport = :8000'
pgrep -af 'uvicorn src.api.app:app'
```

## Chuẩn bị dữ liệu

Chạy:

```bash
PYTHONPATH=. python scripts/prepare_training_data.py
```

Script này tạo/cập nhật:

- `data/processed/thangvip_legalqa/train.jsonl`
- `data/processed/thangvip_legalqa/val.jsonl`
- `data/processed/thangvip_legalqa/test.jsonl`
- `data/aligned/retriever_train.jsonl`
- `data/aligned/reranker_train.jsonl`
- `data/aligned/raft_sft.jsonl`

Lưu ý: ở trạng thái hiện tại, RAFT dataset chưa được xem là hoàn chỉnh và cần tiếp tục build/lọc chất lượng.

## Reindex artifacts

Khi thay đổi corpus/chunks/index:

```bash
PYTHONPATH=. python scripts/reindex.py
```

Sau đó khởi động lại server để load artifacts mới.

## Fine-tune Qwen QLoRA

Smoke train để kiểm tra pipeline:

```bash
PYTHONPATH=. python scripts/train_qwen.py   --config configs/training/runpod.qwen2_5_7b_qlora.smoke.json
```

Train prototype chính:

```bash
PYTHONPATH=. python scripts/train_qwen.py   --config configs/training/runpod.qwen2_5_7b_qlora.json
```

Artifact chính hiện tại:

```text
models/qwen2.5-7b-legalqa-qlora
```

Smoke artifact:

```text
models/qwen2.5-7b-legalqa-qlora-smoke
```

## Evaluation

Answer generation report hiện có:

```text
reports/answer_generation_report.md
reports/answer_generation_report.json
```

Kết quả thử nghiệm ban đầu trên 50 mẫu:

```text
Token F1:          0.4816
ROUGE-L:           0.3811
Citation presence: 0.88
Faithfulness:      0.6973
Reasoning score:   0.2795
```

Các metric trên là heuristic/lexical, chưa phải đánh giá pháp lý cuối cùng.

Chạy answer generation eval:

```bash
PYTHONPATH=. python scripts/eval_answer_generation.py \
  --dataset data/processed/thangvip_legalqa/test.jsonl \
  --limit 50
```

Chạy retrieval eval:

```bash
PYTHONPATH=. python -c '
from src.qa.pipeline import LegalQAPipeline
from src.evaluation.retrieval_eval import evaluate_retrieval
pipeline = LegalQAPipeline.build()
metrics = evaluate_retrieval(
    pipeline,
    qa_path="data/raw/yuitc/test.parquet",
    limit=200,
    top_k=20,
    ks=(1, 5, 10, 20),
)
for key, value in metrics.items():
    print(f"{key}: {value}")
'
```

## Test

Chạy toàn bộ test suite:

```bash
PYTHONPATH=. pytest -q
```

Trạng thái gần nhất:

```text
59 passed
```

## Báo cáo tiến độ

Báo cáo tiến độ hiện có:

```text
reports/progress_report_legalqa_prototype.md
```

Nội dung chính:

- Prototype đã chạy end-to-end với RAG + UI/API + LLM reasoning.
- Đã chuẩn bị dữ liệu SFT/retrieval/reranker.
- Đã có adapter QLoRA Qwen2.5-7B ở mức prototype.
- Chưa hoàn tất RAFT, reranker thật, benchmark retrieval đầy đủ và human evaluation.

## Hướng nghiên cứu tiếp theo

Ưu tiên tiếp theo:

1. Hoàn thiện RAFT dataset từ `yuitc` với positive context, distractor context và refusal samples.
2. Tối ưu/chạy retrieval benchmark chính thức: gold coverage, Recall@1/5/10/20, MRR.
3. Train hoặc tích hợp cross-encoder reranker thật.
4. Chạy ablation: BM25 vs dense vs hybrid, có/không QA-memory, có/không reranker, prompt-only vs SFT vs RAFT.
5. Tạo human review set 100-200 câu để chấm faithfulness, directness, citation correctness và refusal quality.
6. Chuẩn hóa output LLM để giảm tình trạng `forced_raw`.

