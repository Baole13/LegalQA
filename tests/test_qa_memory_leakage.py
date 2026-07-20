from __future__ import annotations

from scripts.audit_qa_memory_leakage import audit_leakage, normalize_question


def test_normalize_question_strips_accents_and_whitespace():
    assert normalize_question("  Thời  hiệu   xử phạt? ") == "thoi hieu xu phat?"


def test_audit_leakage_counts_exact_normalized_and_near_duplicates():
    payload = audit_leakage(
        ["Thời hiệu xử phạt là bao lâu?", "Cơ quan nào có thẩm quyền?"],
        ["Thời hiệu xử phạt là bao lâu?", "Co quan nao co tham quyen?"],
        near_threshold=0.75,
    )

    assert payload["eval_questions"] == 2
    assert payload["qa_memory_questions"] == 2
    assert payload["exact_duplicates"] == 1
    assert payload["normalized_duplicates"] == 2
    assert payload["near_duplicates"] >= 2
    assert payload["max_similarity"] >= 0.75
