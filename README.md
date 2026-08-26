# Vietnamese LegalQA

Prototype hỏi đáp pháp luật tiếng Việt theo hướng **RAG có căn cứ**, kết hợp hybrid retrieval, reranking và Qwen2.5-7B-Instruct với adapter QLoRA.

## Chức năng chính

- Giao diện hỏi đáp tối giản bằng FastAPI và frontend tĩnh.
- Hybrid retrieval từ word sparse, char sparse, embedding model và QA-memory.
- Heuristic reranking, tự động dùng cross-encoder khi artifact khả dụng.
- Sinh câu trả lời có căn cứ, citation, giải thích ngắn và cơ chế từ chối khi thiếu evidence.
- Pipeline chuẩn bị dữ liệu, huấn luyện retriever/reranker/Qwen và đánh giá phục vụ tái lập nghiên cứu.

## Luồng xử lý

```text
Câu hỏi
  -> query expansion và QA-memory
  -> hybrid candidate retrieval
  -> heuristic reranking
  -> optional cross-encoder
  -> top-k evidence
  -> extractive/Qwen generation
  -> câu trả lời + căn cứ + citation
```

## Cấu trúc repository

```text
configs/        Cấu hình dataset, serving, training và ablation
data/           Dữ liệu raw, processed, aligned và retrieval indexes
frontend/       Giao diện hỏi đáp
models/         Ba model artifact được serving sử dụng
reports/        Paper chính và tài liệu chuẩn bị sharing
scripts/        Entrypoint chuẩn bị dữ liệu, train, eval và reindex
src/            Mã nguồn pipeline, API, retrieval, reranking và training
tests/          Test suite
```

Các model runtime được giữ cục bộ:

```text
models/retriever-best
models/reranker-best
models/qwen2.5-7b-legalqa-qlora
```

## Dữ liệu hiện tại

- Corpus: khoảng 643.469 chunks.
- QA-memory: khoảng 89.261 records.
- SFT thangvip: 29.145 records, gồm 26.230 train, 1.457 validation và 1.458 test.
- YUITC được dùng cho corpus retrieval, alignment, retriever/reranker training và evaluation.

## Cài đặt

```bash
cd /workspace/baolq
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Môi trường GPU/RunPod:

```bash
pip install -r requirements-runpod.txt
```

Tạo dense index sau khi có artifact `models/retriever-best` và sparse corpus artifacts:

```bash
PYTHONPATH=. python scripts/build_dense_index.py
```

Retrieval benchmark yêu cầu dense index này và sẽ dừng với hướng dẫn rõ ràng nếu index thiếu hoặc không tương thích.


## Chạy demo

```bash
cd /workspace/baolq
source .venv/bin/activate
uvicorn src.api.app:app --host 127.0.0.1 --port 8000
```

Mở <http://127.0.0.1:8000>. Kiểm tra API:

```bash
curl http://127.0.0.1:8000/health

curl -X POST http://127.0.0.1:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"Theo Khoản 1 Điều 57 Luật Hộ tịch, Cơ sở dữ liệu hộ tịch có tính chất là gì?","top_k":5,"force_llm_reasoning":true}'
```

Các endpoint chính:

- `GET /health`: trạng thái artifact và model.
- `POST /ask`: pipeline hỏi đáp end-to-end.
- `POST /retrieval_debug`: xem kết quả retrieval không chạy generation.
- `POST /reindex`: tạo lại retrieval artifacts.
- `GET /eval`: chạy retrieval evaluation giới hạn.

## Chuẩn bị dữ liệu và huấn luyện

Chuẩn bị toàn bộ dữ liệu:

```bash
PYTHONPATH=. python scripts/prepare_training_data.py
```

Tạo lại indexes:

```bash
PYTHONPATH=. python scripts/reindex.py
```

Huấn luyện:

```bash
PYTHONPATH=. python scripts/train_retriever.py
PYTHONPATH=. python scripts/train_reranker.py
PYTHONPATH=. python scripts/train_qwen.py
```

## Đánh giá

```bash
PYTHONPATH=. python scripts/eval_retrieval.py
PYTHONPATH=. python scripts/eval_answer_generation.py --limit 50
PYTHONPATH=. python scripts/run_paper_experiments.py --limit 300
```

Kết quả tổng hợp được giữ tại:

- `reports/paper_experiments.md/json`
- `reports/paper_draft.md`
- `reports/references.bib`
- `reports/sharing_guide.md`

Các file report trung gian được tạo lại bằng scripts và không lưu trong repository.

## Kiểm thử

```bash
python -m pytest -q
```

## Giới hạn cần lưu ý

- Metric faithfulness/citation/reasoning hiện chủ yếu là proxy, không phải xác nhận độ đúng pháp lý.
- Human evaluation hiện tại chưa phải đánh giá bởi chuyên gia pháp luật.
- Temporal filtering theo hiệu lực văn bản chưa hoàn chỉnh.
- RAFT vẫn là hướng thử nghiệm, chưa phải kết quả serving chính.
- Chất lượng generation phụ thuộc mạnh vào việc retrieval có đưa đúng căn cứ vào top-k hay không.
