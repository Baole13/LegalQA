from src.preprocessing.chunker import build_chunks_from_corpus


def test_hierarchical_chunking_preserves_legal_metadata():
    records = [
        {
            "cid": "vb-01",
            "doc_name": "Bo luat Lao dong",
            "doc_number": "45/2019/QH14",
            "chapter": "VII",
            "effective_date": "2021-01-01",
            "validity_status": "con hieu luc",
            "text": (
                "Dieu 111. Nghi hang nam\n"
                "1. Nguoi lao dong duoc nghi hang nam 12 ngay lam viec.\n"
                "2. Nguoi lam cong viec nang nhoc duoc nghi 14 ngay lam viec."
            ),
        }
    ]

    chunks = build_chunks_from_corpus(records, max_chars=500)

    assert len(chunks) == 2
    assert all(chunk["doc_name"] == "Bo luat Lao dong" for chunk in chunks)
    assert all(chunk["doc_number"] == "45/2019/QH14" for chunk in chunks)
    assert all(chunk["article"] == "111" for chunk in chunks)
    assert {chunk["clause"] for chunk in chunks} == {"1", "2"}
    assert all(chunk["chunk_level"] == "clause" for chunk in chunks)


def test_hierarchical_chunking_falls_back_to_article_when_no_clause_exists():
    records = [
        {
            "cid": "vb-02",
            "doc_name": "Luat Mau",
            "text": "Dieu 5. Co quan co tham quyen la Uy ban nhan dan cap tinh.",
        }
    ]

    chunks = build_chunks_from_corpus(records, max_chars=500)

    assert len(chunks) == 1
    assert chunks[0]["article"] == "5"
    assert chunks[0]["clause"] is None
    assert chunks[0]["chunk_level"] == "article"
