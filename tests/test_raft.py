from src.training.raft import build_raft_training_records


def test_build_raft_training_records_creates_positive_and_distractor_samples(monkeypatch):
    monkeypatch.setattr(
        "src.training.raft.load_qa_records",
        lambda _: [
            {
                "qid": "q1",
                "question": "Nguoi lao dong duoc nghi bao nhieu ngay phep nam?",
                "answer": "Nguoi lao dong duoc nghi hang nam 12 ngay lam viec.",
            }
        ],
    )

    aligned_pairs = [
        {
            "qa_id": "q1",
            "query": "Nguoi lao dong duoc nghi bao nhieu ngay phep nam?",
            "gold_cids": ["1"],
            "positive_chunk_id": "1:0",
            "positive_cid": "1",
            "positive_text": "Dieu 111. Nguoi lao dong duoc nghi hang nam 12 ngay lam viec.",
        }
    ]
    retrieval_lookup = {
        "Nguoi lao dong duoc nghi bao nhieu ngay phep nam?": [
            {"chunk_id": "1:0", "cid": "1", "text": "Dieu 111. Nguoi lao dong duoc nghi hang nam 12 ngay lam viec."},
            {"chunk_id": "2:0", "cid": "2", "text": "Dieu 112. Quy dinh ve tam hoan hop dong lao dong."},
            {"chunk_id": "3:0", "cid": "3", "text": "Dieu 113. Quy dinh ve thu tuc bao cao."},
        ]
    }

    records = build_raft_training_records(aligned_pairs, retrieval_lookup)

    assert len(records) == 1
    assert records[0]["contains_answer"] is True
    assert records[0]["contexts"][0]["is_gold"] is True
    assert records[0]["target"] == "Nguoi lao dong duoc nghi hang nam 12 ngay lam viec."
