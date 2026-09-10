# Benchmark Results

This directory contains official benchmark results for the Vietnamese LegalQA system.

## File Index

| File | Phase | Description |
|---|---|---|
| `retrieval_benchmark.csv` | Phase 1 | Official retrieval benchmark on YuITC test set (all 6 variants) |
| `retrieval_benchmark.json` | Phase 1 | Full metrics + bootstrap CIs |
| `retrieval_public_benchmark.csv` | Phase 2 | Public dense model comparison (BGE-M3, E5) |
| `reranker_benchmark.csv` | Phase 3 | Public reranker comparison |
| `generation_benchmark.csv` | Phase 4 | Generation configurations comparison |
| `generation_details_*.jsonl` | Phase 4 | Per-sample generation results |
| `reasoning_analysis.csv` | Phase 5 | Breakdown by question type and difficulty |
| `topk_analysis.csv` | Phase 6 | Oracle vs retrieved top-k analysis |
| `ablation.csv` | Phase 9 | Component ablation study |
| `error_analysis.md` | Phase 7 | Systematic error analysis |
| `error_analysis.json` | Phase 7 | Structured error data |
| `metric_correlation.md` | Phase 8 | Auto vs human metric correlation |
| `metric_correlation.json` | Phase 8 | Structured correlation data |

## Reproducibility

All scripts are in `scripts/benchmark_*.py`. Each script:
- Uses the same corpus index (`data/indexes/`)
- Caches intermediate results to `reports/.benchmark_cache/official_*/`
- Can be re-run to verify results

## Benchmark Conditions (Fixed Across All Experiments)

- **Dataset:** YuITC (`data/raw/yuitc/test.parquet`)
- **Generation dataset:** Thangvip (`data/processed/thangvip_legalqa/test.jsonl`)
- **Corpus:** `data/processed/chunks_v3.jsonl` (643,469 chunks)
- **Top-k:** 20 for retrieval, 5 for generation context
- **Sample size:** 1,000 for official retrieval; 200 for generation (due to compute)
- **Metrics:** Recall@1/5/10/20, MRR@10, nDCG@10, Token F1, ROUGE-L

## Running the Full Benchmark

```bash
# Phase 1 — Official retrieval benchmark
python scripts/benchmark_retrieval_official.py --limit 1000

# Phase 2 — Public dense models (requires GPU + internet)
python scripts/benchmark_public_dense.py --limit 300

# Phase 3 — Public reranker comparison
python scripts/benchmark_public_reranker.py --limit 300

# Phase 4 — Generation benchmark (requires GPU)
python scripts/benchmark_generation.py --limit 200

# Phase 5 — Reasoning analysis (after Phase 4)
python scripts/benchmark_reasoning_analysis.py

# Phase 6 — Top-k analysis (requires GPU)
python scripts/benchmark_topk_analysis.py --limit 100

# Phase 7 — Error analysis
python scripts/error_analysis.py

# Phase 8 — Metric correlation
python scripts/analyze_metric_correlation.py

# Phase 9 — Ablation (uses Phase 1 cache)
python scripts/benchmark_ablation.py
```
