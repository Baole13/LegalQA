from src.qa.generator import ExtractiveAnswerGenerator
from src.utils.text import detect_question_intent, direct_answer_score


def test_detect_question_intent_for_common_legal_patterns():
    assert detect_question_intent("Nguoi lao dong duoc nghi bao nhieu ngay phep nam?") == "quantity"
    assert detect_question_intent("Ai co tham quyen ra quyet dinh thanh lap hoi dong?") == "authority"
    assert detect_question_intent("Co phai bao cao dinh ky hang nam khong?") == "yes_no"


def test_direct_answer_score_prefers_substantive_answer_over_procedure():
    question = "Nguoi lao dong duoc nghi bao nhieu ngay phep nam?"
    direct_text = "Nguoi lao dong duoc nghi hang nam 12 ngay lam viec; truong hop nang nhoc duoc 14 ngay."
    procedural_text = "Khi co nhu cau nghi phep, phai gui don xin nghi den thu truong truoc 01 ngay."
    assert direct_answer_score(question, direct_text) > direct_answer_score(question, procedural_text)


def test_generator_hides_qa_memory_from_user_facing_citations():
    generator = ExtractiveAnswerGenerator()
    result = generator.generate(
        "Ai co tham quyen ra quyet dinh thanh lap hoi dong?",
        [
            {
                "chunk_id": "qa-memory:1:0",
                "cid": "1",
                "title": "QA Memory",
                "article": None,
                "clause": None,
                "text": "Giam doc So Y te ra quyet dinh thanh lap hoi dong.",
                "hybrid_score": 5.0,
                "rerank_score": 5.0,
                "qa_boost": 0.8,
            },
            {
                "chunk_id": "62339",
                "cid": "62339",
                "title": "Thong tu 07/2018/TT-BYT",
                "article": "23",
                "clause": "1",
                "text": "Dieu 23. Giam doc So Y te ra quyet dinh thanh lap Hoi dong tu van cap Chung chi hanh nghe duoc theo hinh thuc xet ho so.",
                "hybrid_score": 4.8,
                "rerank_score": 6.0,
                "qa_boost": 0.0,
            },
        ],
    )
    assert result["citations"]
    assert all(not item["chunk_id"].startswith("qa-memory:") for item in result["citations"])
    assert "Thong tu 07/2018/TT-BYT" in result["answer"]
