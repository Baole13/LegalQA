from src.qa.prompt_builder import build_reasoning_prompt


def test_prompt_builder_uses_top_five_evidence():
    evidence = [
        {"chunk_id": f"c{i}", "cid": str(i), "article": None, "clause": None, "text": f"text {i}"}
        for i in range(6)
    ]
    prompt = build_reasoning_prompt("question", evidence)
    assert '"chunk_id": "c0"' in prompt
    assert '"chunk_id": "c4"' in prompt
    assert '"chunk_id": "c5"' not in prompt


def test_prompt_builder_includes_question_intent():
    prompt = build_reasoning_prompt(
        "Ai co tham quyen quyet dinh thanh lap hoi dong?",
        [{"chunk_id": "c1", "cid": "1", "article": None, "clause": None, "text": "text"}],
    )
    assert "Loai cau hoi:" in prompt
    assert "authority" in prompt


def test_prompt_builder_requires_i_do_not_know_when_context_missing():
    prompt = build_reasoning_prompt(
        "Thong tin nay co trong van ban nao?",
        [{"chunk_id": "c1", "cid": "1", "article": None, "clause": None, "text": "text"}],
    )
    assert 'Toi khong biet' in prompt
