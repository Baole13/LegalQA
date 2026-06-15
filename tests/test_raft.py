from src.training.raft import RaftBuildConfig, build_raft_records_from_retrieval_records, build_raft_training_records


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



def test_build_raft_records_from_yuitc_retrieval_records_writes_grounded_and_refusal_samples(tmp_path):
    records = [
        {
            "query_id": "q1",
            "question": "Nguoi lao dong duoc nghi bao nhieu ngay phep nam?",
            "positive_context": "Dieu 113. Nguoi lao dong duoc nghi hang nam 12 ngay lam viec.",
            "positive_cids": ["1"],
            "doc_name": "Bo luat Lao dong",
        },
        {
            "query_id": "q2",
            "question": "Ai thanh lap hoi dong?",
            "positive_context": "Giam doc So Y te ra quyet dinh thanh lap Hoi dong.",
            "positive_cids": ["2"],
            "doc_name": "Thong tu Y te",
        },
        {
            "query_id": "q3",
            "question": "Khi nao tam hoan hop dong?",
            "positive_context": "Hop dong lao dong duoc tam hoan trong cac truong hop theo luat.",
            "positive_cids": ["3"],
            "doc_name": "Bo luat Lao dong",
        },
    ]

    built = build_raft_records_from_retrieval_records(
        records,
        RaftBuildConfig(output_path=str(tmp_path / "raft.jsonl"), positive_ratio=0.5, contexts_per_sample=3),
    )

    assert any(item["contains_answer"] for item in built)
    assert any(not item["contains_answer"] for item in built)
    positive = next(item for item in built if item["contains_answer"])
    assert positive["contexts"][0]["is_gold"] is True
    assert "Tra loi:" in positive["target"]
    assert "Can cu:" in positive["target"]
