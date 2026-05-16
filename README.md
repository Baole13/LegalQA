# LegalQA

Du an nay da duoc dieu chinh theo pipeline LegalQA cho bai toan tieng Viet theo huong:

1. Data pipeline phap ly co metadata day du.
2. Hybrid retrieval: dense + sparse + optional Elasticsearch.
3. Reranking truoc khi dua vao LLM.
4. Answer generation bi rang buoc boi context va citation.
5. RAFT-style fine-tune dataset cho Qwen tren RunPod GPU A40.

## Kien truc moi

```text
configs/
  serving/
  training/
data/
  aligned/
  evaluation/
  raw/
scripts/
src/
  alignment/
  api/
  data/
  indexing/
  preprocessing/
  qa/
  reranker/
  retrieval/
  training/
  utils/
tests/
```

## Pipeline dung theo yeu cau moi

### 1. Xu ly va chuan bi du lieu

- Ingest tu PDF / Word / Parquet vao `data/corpus.parquet`.
- Chuan hoa record ve schema chung trong `src/preprocessing/legal_metadata.py`.
- Lam sach OCR / khoang trang / metadata.
- Hierarchical chunking trong `src/preprocessing/chunker.py`:
  - uu tien cat theo `Dieu`
  - neu co `Khoan` thi tach tiep theo `Khoan`
  - chi fallback sang window nho hon khi dieu/khoan qua dai
- Moi chunk giu metadata:
  - `doc_name`
  - `doc_number`
  - `chapter`
  - `article`
  - `clause`
  - `issued_date`
  - `effective_date`
  - `expiry_date`
  - `validity_status`
  - `source_path`
  - `source_type`
  - `chunk_level`

Config tham khao: `configs/training/data_pipeline.legal.json`

### 2. Hybrid retrieval va rerank

- `src/retrieval/bm25_retriever.py`: bat tu khoa, so dieu, so hieu.
- `src/retrieval/dense_retriever.py` va `embedding_ensemble.py`: bat y nghia cau hoi tieng Viet.
- `src/retrieval/hybrid_retriever.py`: hop nhat sparse + dense + QA memory + optional Elasticsearch.
- `src/reranker/model_reranker.py`: rerank top-N de dua dung dieu khoan len tren.

Config retrieval: `configs/serving/retrieval.hybrid.json`

### 3. Generation va citation

- `src/qa/prompt_builder.py` rang buoc LLM:
  - chi duoc dua tren evidence
  - neu context khong co cau tra loi thi phai tra `Toi khong biet`
- `src/qa/citation_formatter.py` tao citation theo ten van ban, so hieu, chuong, dieu, khoan, trang thai hieu luc.
- `src/qa/generator.py` uu tien answer extractive va chi goi Qwen khi evidence du manh.

### 4. Fine-tune theo RAFT

Builder moi: `src/training/raft.py`

Moi record SFT co dang:

```json
{
  "question": "...",
  "contexts": [
    {
      "chunk_id": "...",
      "cid": "...",
      "doc_name": "...",
      "doc_number": "...",
      "article": "...",
      "clause": "...",
      "text": "...",
      "is_gold": true
    }
  ],
  "target": "...",
  "contains_answer": true
}
```

Ty le mac dinh:
- 80% mau co context chua dap an dung
- 20% mau distractor, target = `Toi khong biet.`

Config tham khao: `configs/training/raft.sft.json`

## Huong van hanh tren RunPod A40 voi Qwen

### Cai dat

```bash
pip install -r requirements.txt
pip install -r requirements-runpod.txt
```

### Build artifacts

```bash
python scripts/reindex.py
```

### Sinh du lieu train cho retriever, reranker, RAFT

```bash
python scripts/prepare_training_data.py
```

Output:
- `data/aligned/aligned_pairs.jsonl`
- `data/aligned/retriever_train.jsonl`
- `data/aligned/reranker_train.jsonl`
- `data/aligned/raft_sft.jsonl`

### Chay API

```bash
uvicorn src.api.app:app --reload
```

### Cau hinh Qwen

Mac dinh repo dang uu tien `configs/serving/llm.qwen.json`.

Bien moi truong huu ich:

```bash
LEGAL_QA_USE_LLM_REASONING=1
LEGAL_QA_LLM_CONFIG_PATH=configs/serving/llm.qwen.json
LEGAL_QA_RETRIEVER_CONFIG_PATH=configs/serving/retrieval.hybrid.json
```

## Goi y roadmap tiep theo

1. Bo sung parser PDF/Word -> parquet co OCR cleaning manh hon.
2. Dung embedding tieng Viet tot nhat ma ban co tren A40 de lam dense retriever.
3. Train reranker bang hard negatives tu corpora phap ly that.
4. Fine-tune Qwen bang `raft_sft.jsonl`.
5. Them evaluation cho citation accuracy, refusal accuracy, recall theo dieu/khoan.

## Kiem tra

```bash
pytest -q tests
```
