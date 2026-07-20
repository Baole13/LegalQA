from __future__ import annotations

from scripts.eval_answer_generation import (
    SCHEMA_PROMPT_INSTRUCTION,
    _annotate_baseline_distinctness,
    _render_prompt,
    _sample_with_context,
)

from src.evaluation.answer_eval import (
    AnswerEvalSample,
    clean_generation_output,
    evaluate_answer_generation,
    load_answer_eval_samples,
    render_eval_prompt,
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
    assert metrics["format_compliance"] == 1.0
    assert metrics["citation_presence"] == 1.0
    assert metrics["reasoning_score"] > 0.5
    assert metrics["faithfulness_score"] > 0.0


def test_clean_generation_output_removes_chat_prefix_and_keeps_raw_prediction():
    samples = [
        AnswerEvalSample(
            question="Bao nhieu ngay?",
            context="Dieu 113. Nguoi lao dong duoc nghi 12 ngay.",
            gold_answer="Duoc nghi 12 ngay.",
            prompt="User: prompt",
            metadata={},
        )
    ]

    def generate_fn(_sample):
        return "Human: noisy prompt\nAssistant: Can cu phap ly: Dieu 113. Ket luan: Duoc nghi 12 ngay."

    metrics = evaluate_answer_generation(samples, generate_fn)
    detail = metrics["details"][0]
    assert "Human:" not in detail["prediction_text"]
    assert not detail["prediction_text"].startswith("Assistant:")
    assert "Human:" in detail["raw_prediction"]


def test_clean_generation_output_parses_json_fence():
    cleaned = clean_generation_output('```json\n{"answer":"Duoc nghi 12 ngay","citation_chunk_ids":["113"]}\n```')
    assert isinstance(cleaned, dict)
    assert cleaned["answer"] == "Duoc nghi 12 ngay"


def test_render_eval_prompt_uses_chat_template_when_available():
    class DummyTokenizer:
        def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=False):
            assert add_generation_prompt is True
            assert all(message["role"] != "assistant" for message in messages)
            return "CHAT_TEMPLATE_PROMPT"

    sample = AnswerEvalSample(
        question="q",
        context="c",
        gold_answer="a",
        prompt="fallback",
        metadata={},
        messages=({"role": "user", "content": "hello"}, {"role": "assistant", "content": "answer"}),
    )
    assert render_eval_prompt(sample, tokenizer=DummyTokenizer()) == "CHAT_TEMPLATE_PROMPT"


def test_schema_prompt_adds_json_instruction_without_assistant_message():
    captured = {}

    class DummyTokenizer:
        def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=False):
            captured["messages"] = messages
            return "SCHEMA_CHAT_TEMPLATE"

    sample = AnswerEvalSample(
        question="q",
        context="c",
        gold_answer="a",
        prompt="fallback",
        metadata={},
        messages=(
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "Question?"},
            {"role": "assistant", "content": "gold"},
        ),
    )

    rendered = _render_prompt(sample, tokenizer=DummyTokenizer(), prompt_style="schema")

    assert rendered == "SCHEMA_CHAT_TEMPLATE"
    assert SCHEMA_PROMPT_INSTRUCTION in captured["messages"][-1]["content"]
    assert all(message["role"] != "assistant" for message in captured["messages"])
    assert SCHEMA_PROMPT_INSTRUCTION not in _render_prompt(sample, prompt_style="default")


def test_oracle_baseline_marked_not_distinct_when_metrics_match_prompt_only():
    rows = _annotate_baseline_distinctness(
        [
            {"variant": "qwen_prompt_only", "token_f1": 0.5, "rouge_l": 0.4, "format_compliance": 0.0},
            {"variant": "oracle_evidence_qwen", "token_f1": 0.5, "rouge_l": 0.4, "format_compliance": 0.0},
        ]
    )
    oracle = next(row for row in rows if row["variant"] == "oracle_evidence_qwen")

    assert oracle["status"] == "not_distinct"
    assert oracle["exclude_from_main_table"] is True
    assert "not a distinct" in oracle["diagnostic_note"]


def test_sample_with_context_replaces_oracle_context_in_prompt_and_messages():
    sample = AnswerEvalSample(
        question="Muc phat la bao nhieu?",
        context="old context",
        gold_answer="answer",
        prompt="User: fallback",
        metadata={"id": "s1"},
        messages=(
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "Van ban phap ly:\nOLD\n\nCau hoi:\nMuc phat la bao nhieu?\n\nYeu cau:\nTra loi."},
            {"role": "assistant", "content": "answer"},
        ),
    )

    updated = _sample_with_context(
        sample,
        "[CID: 1] retrieved legal evidence",
        [{"cid": "1", "chunk_id": "1", "text": "retrieved legal evidence", "rerank_score": 0.9}],
    )

    user_message = next(message for message in updated.messages if message["role"] == "user")
    assert updated.context == "[CID: 1] retrieved legal evidence"
    assert "retrieved legal evidence" in user_message["content"]
    assert "OLD" not in user_message["content"]
    assert updated.metadata["evidence_mode"] == "retrieved_context"
    assert updated.metadata["retrieved"][0]["cid"] == "1"
