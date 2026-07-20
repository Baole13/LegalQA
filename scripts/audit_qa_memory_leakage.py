from __future__ import annotations

import argparse
import json
from pathlib import Path

import scripts._bootstrap as _bootstrap

from src.evaluation.answer_eval import load_answer_eval_samples
from src.utils.io import load_jsonl
from src.utils.text import normalize_text, strip_accents


def normalize_question(text: str) -> str:
    normalized = strip_accents(normalize_text(str(text or ""))).lower()
    return " ".join(normalized.split())


def load_eval_questions(path: str | Path, limit: int = 0) -> list[str]:
    samples = load_answer_eval_samples(path, limit=limit)
    return [sample.question for sample in samples if sample.question]


def load_qa_memory_questions(path: str | Path) -> list[str]:
    rows = load_jsonl(path)
    return [str(row.get("question", "")).strip() for row in rows if str(row.get("question", "")).strip()]


def audit_leakage(eval_questions: list[str], qa_questions: list[str], near_threshold: float = 0.9) -> dict:
    eval_norm = [normalize_question(item) for item in eval_questions]
    qa_norm = [normalize_question(item) for item in qa_questions]
    qa_exact = set(item.strip() for item in qa_questions)
    qa_norm_set = set(qa_norm)

    exact_examples = []
    normalized_examples = []
    for question, norm in zip(eval_questions, eval_norm):
        if question.strip() in qa_exact:
            exact_examples.append({"question": question})
        if norm and norm in qa_norm_set:
            normalized_examples.append({"question": question, "normalized_question": norm})

    near = _near_duplicate_examples(eval_questions, eval_norm, qa_questions, qa_norm, near_threshold)
    max_similarity = max((item["similarity"] for item in near), default=0.0)
    return {
        "eval_questions": len(eval_questions),
        "qa_memory_questions": len(qa_questions),
        "near_threshold": near_threshold,
        "exact_duplicates": len(exact_examples),
        "normalized_duplicates": len(normalized_examples),
        "near_duplicates": len(near),
        "max_similarity": round(max_similarity, 4),
        "examples": {
            "exact_duplicates": exact_examples[:10],
            "normalized_duplicates": normalized_examples[:10],
            "near_duplicates": near[:10],
        },
    }


def _near_duplicate_examples(
    eval_questions: list[str],
    eval_norm: list[str],
    qa_questions: list[str],
    qa_norm: list[str],
    threshold: float,
) -> list[dict]:
    if not eval_norm or not qa_norm:
        return []
    try:
        from sklearn.feature_extraction.text import HashingVectorizer
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("Missing scikit-learn for near-duplicate audit.") from exc

    vectorizer = HashingVectorizer(
        analyzer="char_wb",
        n_features=2**18,
        alternate_sign=False,
        norm="l2",
        ngram_range=(3, 5),
        lowercase=False,
    )
    qa_matrix = vectorizer.transform(qa_norm)
    qa_transposed = qa_matrix.T.tocsr()
    eval_matrix = vectorizer.transform(eval_norm)
    examples: list[dict] = []
    batch_size = 128
    for start in range(0, len(eval_questions), batch_size):
        stop = min(start + batch_size, len(eval_questions))
        scores = (eval_matrix[start:stop] @ qa_transposed).tocsr()
        for local_index, question in enumerate(eval_questions[start:stop]):
            row = scores.getrow(local_index)
            if row.nnz == 0:
                continue
            best_local = int(row.data.argmax())
            best_pos = int(row.indices[best_local])
            best_score = float(row.data[best_local])
            if best_score >= threshold:
                examples.append(
                    {
                        "question": question,
                        "qa_memory_question": qa_questions[best_pos],
                        "similarity": round(best_score, 4),
                    }
                )
    examples.sort(key=lambda item: item["similarity"], reverse=True)
    return examples


def render_markdown(payload: dict) -> str:
    lines = [
        "# QA-Memory Leakage Audit",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Eval questions | {payload.get('eval_questions', 0)} |",
        f"| QA-memory questions | {payload.get('qa_memory_questions', 0)} |",
        f"| Exact duplicates | {payload.get('exact_duplicates', 0)} |",
        f"| Normalized duplicates | {payload.get('normalized_duplicates', 0)} |",
        f"| Near duplicates >= {payload.get('near_threshold', '')} | {payload.get('near_duplicates', 0)} |",
        f"| Max similarity | {payload.get('max_similarity', 0.0)} |",
    ]
    near = payload.get("examples", {}).get("near_duplicates", [])
    if near:
        lines.extend(["", "## Top Near-Duplicate Examples", "", "| Similarity | Eval question | QA-memory question |", "|---:|---|---|"])
        for item in near[:10]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(item.get("similarity", "")),
                        _cell(item.get("question", "")),
                        _cell(item.get("qa_memory_question", "")),
                    ]
                )
                + " |"
            )
    return "\n".join(lines) + "\n"


def _cell(value: object, max_len: int = 180) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    return text[: max_len - 3] + "..." if len(text) > max_len else text


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit exact and near duplicates between evaluation questions and QA-memory.")
    parser.add_argument("--eval-dataset", default="data/processed/thangvip_legalqa/test.jsonl")
    parser.add_argument("--qa-memory", default="data/processed/qa_memory_v3.jsonl")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--near-threshold", type=float, default=0.9)
    parser.add_argument("--report-dir", default="reports")
    args = parser.parse_args()

    eval_questions = load_eval_questions(args.eval_dataset, limit=args.limit)
    qa_questions = load_qa_memory_questions(args.qa_memory)
    payload = audit_leakage(eval_questions, qa_questions, near_threshold=args.near_threshold)
    payload["eval_dataset"] = args.eval_dataset
    payload["qa_memory"] = args.qa_memory

    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "qa_memory_leakage_audit.json"
    md_path = report_dir / "qa_memory_leakage_audit.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"Saved: {json_path}")
    print(f"Saved: {md_path}")


if __name__ == "__main__":
    main()
