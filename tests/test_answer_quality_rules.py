from src.qa.generator import ExtractiveAnswerGenerator
from src.utils.text import detect_question_intent, direct_answer_score, infer_document_title, topic_anchor_score


def test_detect_question_intent_for_common_legal_patterns():
    assert detect_question_intent("Nguoi lao dong duoc nghi bao nhieu ngay phep nam?") == "quantity"
    assert detect_question_intent("Ai co tham quyen ra quyet dinh thanh lap hoi dong?") == "authority"
    assert detect_question_intent("Co phai bao cao dinh ky hang nam khong?") == "yes_no"


def test_direct_answer_score_prefers_substantive_answer_over_procedure():
    question = "Nguoi lao dong duoc nghi bao nhieu ngay phep nam?"
    direct_text = "Nguoi lao dong duoc nghi hang nam 12 ngay lam viec; truong hop nang nhoc duoc 14 ngay."
    procedural_text = "Khi co nhu cau nghi phep, phai gui don xin nghi den thu truong truoc 01 ngay."
    assert direct_answer_score(question, direct_text) > direct_answer_score(question, procedural_text)


def test_topic_anchor_penalizes_overtime_rule_for_annual_leave_question():
    question = "Nguoi lao dong duoc nghi bao nhieu ngay phep nam?"
    annual_leave_text = "Nguoi lao dong duoc nghi hang nam 12 ngay lam viec."
    overtime_text = "Nguoi lao dong di lam vao ngay nghi duoc tra it nhat 300% tien luong."
    assert topic_anchor_score(question, annual_leave_text) > topic_anchor_score(question, overtime_text)


def test_infer_document_title_does_not_treat_full_sentence_as_title():
    text = "Nguoi lao dong co du 12 thang lam viec cho nguoi su dung lao dong thi duoc nghi hang nam va duoc huong nguyen luong theo Bo luat Lao dong."
    assert infer_document_title(text) is None


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
    assert result["legal_basis"]
    assert all(not item["chunk_id"].startswith("qa-memory:") for item in result["citations"])
    assert "Thong tu 07/2018/TT-BYT" in result["legal_basis"][0]
    assert "Giam doc So Y te" in result["answer"]


def test_generator_prefers_annual_leave_answer_over_overtime_percentage():
    generator = ExtractiveAnswerGenerator()
    result = generator.generate(
        "Nguoi lao dong duoc nghi bao nhieu ngay phep nam?",
        [
            {
                "chunk_id": "ot-1",
                "cid": "ot",
                "title": "Bo luat Lao dong",
                "article": "98",
                "clause": "1",
                "text": "Nguoi lao dong di lam vao ngay nghi duoc tra it nhat 300% tien luong.",
                "hybrid_score": 8.0,
                "rerank_score": 8.0,
                "qa_boost": 0.0,
            },
            {
                "chunk_id": "leave-1",
                "cid": "leave",
                "title": "Bo luat Lao dong",
                "article": "113",
                "clause": "1",
                "text": "Nguoi lao dong duoc nghi hang nam 12 ngay lam viec.",
                "hybrid_score": 7.5,
                "rerank_score": 7.5,
                "qa_boost": 0.0,
            },
        ],
    )
    assert "12 ngay" in result["answer"]
    assert "300%" not in result["answer"]



def test_generator_prefers_default_annual_leave_days_over_partial_year_formula():
    generator = ExtractiveAnswerGenerator()
    result = generator.generate(
        "Người lao động được nghỉ bao nhiêu ngày phép năm?",
        [
            {
                "chunk_id": "formula-1",
                "cid": "formula",
                "title": "Bo luat Lao dong",
                "article": "65",
                "clause": "1",
                "text": "Số ngày nghỉ hằng năm của người lao động làm việc chưa đủ 12 tháng theo quy định tại khoản 2 Điều 113 của Bộ luật Lao động được tính như sau: lấy số ngày nghỉ hằng năm chia cho 12 tháng, nhân với số tháng làm việc thực tế.",
                "hybrid_score": 9.0,
                "rerank_score": 9.0,
                "qa_boost": 0.7,
            },
            {
                "chunk_id": "leave-1",
                "cid": "leave",
                "title": "Bo luat Lao dong",
                "article": "113",
                "clause": "1",
                "text": "Người lao động làm việc đủ 12 tháng cho một người sử dụng lao động thì được nghỉ hằng năm 12 ngày làm việc đối với người làm công việc trong điều kiện bình thường.",
                "hybrid_score": 8.0,
                "rerank_score": 8.0,
                "qa_boost": 0.0,
            },
        ],
    )
    assert "12 ngày" in result["answer"]
    assert "chưa đủ 12 tháng" not in result["answer"]
