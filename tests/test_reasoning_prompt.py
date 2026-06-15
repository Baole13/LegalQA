from src.qa.prompt_builder import build_reasoning_prompt


def test_build_reasoning_prompt_requires_concise_grounded_json():
    prompt = build_reasoning_prompt(
        question="Nguoi lao dong duoc nghi bao nhieu ngay?",
        evidence_chunks=[
            {
                "chunk_id": "1:0",
                "cid": "1",
                "doc_name": "Bo luat Lao dong",
                "article": "113",
                "clause": "1",
                "text": "Nguoi lao dong duoc nghi hang nam 12 ngay lam viec.",
            }
        ],
        draft_answer="Duoc nghi 12 ngay.",
    )
    assert '"answer"' in prompt
    assert '"legal_basis"' in prompt
    assert '"reasoning"' in prompt
    assert '"missing_info"' in prompt
    assert '"structured_answer"' not in prompt
