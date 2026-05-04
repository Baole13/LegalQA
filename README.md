# Legal QA Project

Repository này đã được tổ chức lại theo cấu trúc một dự án Legal QA hoàn chỉnh hơn, với các nhóm thư mục rõ ràng cho `docs`, `configs`, `data`, `scripts`, `src`, `notebooks`, và `tests`.

## Cấu trúc repo

```text
docs/
  plans/
configs/
  environments/
  serving/
  training/
data/
  raw/
  processed/
  aligned/
  indexes/
  evaluation/
frontend/
notebooks/
scripts/
src/
tests/
```

## Ý nghĩa các thư mục

- `configs/serving/`: cấu hình serving và Qwen reasoning
- `configs/training/`: cấu hình fine-tune retriever/reranker
- `configs/environments/`: env mẫu cho RunPod
- `data/raw/`: dữ liệu thô nếu mở rộng thêm nguồn
- `data/processed/`: artifact đã xử lý
- `data/aligned/`: training pairs, hard negatives
- `data/indexes/`: retrieval artifacts
- `data/evaluation/`: gold set, manual eval, metric outputs
- `scripts/`: orchestration scripts
- `src/`: source code chính
- `tests/`: test cases
- `notebooks/`: notebooks nghiên cứu

## Config chính

Serving:

- `configs/serving/serving.json`
- `configs/serving/llm.qwen.json`

Training:

- `configs/training/retriever.train.json`
- `configs/training/reranker.train.json`

Environment:

- `configs/environments/runpod.env.example`

## Cài đặt

Dev/local:

```bash
pip install -r requirements.txt
```

RunPod / fine-tune / reasoning:

```bash
pip install -r requirements-runpod.txt
```

## Chạy cơ bản

```bash
python scripts/reindex.py
uvicorn src.api.app:app --reload
```

## Flow RunPod

```bash
python scripts/runpod_bootstrap.py
python scripts/train_retriever.py
python scripts/train_reranker.py
python scripts/runpod_healthcheck.py
uvicorn src.api.app:app --host 0.0.0.0 --port 8000
```
