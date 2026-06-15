from __future__ import annotations

from src.evaluation.answer_eval import (
    AnswerEvalSample,
    evaluate_answer_generation,
    load_answer_eval_samples,
)


def test_load_answer_eval_samples_parses_sft_jsonl(tmp_path):
    path = tmp_path / "sample.jsonl"
    path.write_text(
        "\n".join(
            [
                '{"messages":[{"role":"system","content":"sys"},{"role":"user","content":"Van ban phap ly:\\nDieu 113.\\n\\nCau hoi:\\nBao nhieu ngay?\\n\\nYeu cau:\\nTra loi."},{"role":"assistant","content":"Can cu phap ly:\\n- Dieu 113"}],"metadata":{"id":1}}'
            ]
        ),
        encoding="utf-8",
    )
    samples = load_answer_eval_samples(path)
    assert len(samples) == 1
    assert samples[0].question == "Bao nhieu ngay?"
    assert "Dieu 113" in samples[0].context


def test_evaluate_answer_generation_computes_basic_metrics():
    samples = [
        AnswerEvalSample(
            question="Bao nhieu ngay?",
            context="Dieu 113. Nguoi lao dong duoc nghi 12 ngay.",
            gold_answer="Can cu phap ly:\n- Dieu 113\n\nKet luan:\n- Duoc nghi 12 ngay.",
            prompt="",
            metadata={},
        )
    ]

    def generate_fn(_sample):
        return (
            "Can cu phap ly:\n"
            "- Dieu 113\n\n"
            "Dieu kien phap ly lien quan:\n"
            "- Du 12 thang lam viec\n\n"
            "Ap dung vao tinh huong:\n"
            "- Nguoi lao dong da du dieu kien\n\n"
            "Ket luan:\n"
            "- Duoc nghi 12 ngay\n\n"
            "Thong tin con thieu:\n"
            "- Khong co them thong tin can bo sung."
        )

    metrics = evaluate_answer_generation(samples, generate_fn)
    assert metrics["samples"] == 1
    assert metrics["structure_score"] == 1.0
    assert metrics["citation_presence"] == 1.0
    assert metrics["reasoning_score"] > 0.5
    assert metrics["faithfulness_score"] > 0.0
