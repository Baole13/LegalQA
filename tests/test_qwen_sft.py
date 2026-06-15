from src.training.qwen_sft import build_qwen_sft_records, build_sft_prompt, format_contexts


def test_format_contexts_includes_legal_metadata():
    text = format_contexts(
        [
            {
                "doc_name": "Bo luat Lao dong",
                "doc_number": "45/2019/QH14",
                "article": "113",
                "clause": "1",
                "text": "Nguoi lao dong duoc nghi hang nam 12 ngay lam viec.",
            }
        ]
    )
    assert "Bo luat Lao dong | So 45/2019/QH14 | Dieu 113 | Khoan 1" in text
    assert "12 ngay lam viec" in text


def test_build_sft_prompt_mentions_context_and_refusal_rule():
    prompt = build_sft_prompt(
        question="Nguoi lao dong duoc nghi bao nhieu ngay phep nam?",
        contexts=[
            {
                "doc_name": "Bo luat Lao dong",
                "article": "113",
                "clause": "1",
                "text": "Nguoi lao dong duoc nghi hang nam 12 ngay lam viec.",
            }
        ],
        instruction_template="Chi duoc tra loi dua tren chung cu.",
    )
    assert "Cau hoi:" in prompt
    assert "Chung cu phap ly:" in prompt
    assert "Toi khong biet" in prompt


def test_build_qwen_sft_records_uses_target_answer():
    records = build_qwen_sft_records(
        [
            {
                "question": "Nguoi lao dong duoc nghi bao nhieu ngay phep nam?",
                "target": "Nguoi lao dong duoc nghi hang nam 12 ngay lam viec.",
                "contexts": [
                    {
                        "doc_name": "Bo luat Lao dong",
                        "article": "113",
                        "clause": "1",
                        "text": "Nguoi lao dong duoc nghi hang nam 12 ngay lam viec.",
                    }
                ],
            }
        ],
        instruction_template="Chi duoc tra loi dua tren chung cu.",
    )
    assert len(records) == 1
    assert "Nguoi lao dong duoc nghi bao nhieu ngay phep nam?" in records[0].prompt
    assert records[0].answer == "Nguoi lao dong duoc nghi hang nam 12 ngay lam viec."
