from src.data.prepare_retrieval_data import RetrievalBuildConfig, build_retrieval_training_sets
from src.utils.io import load_json, load_jsonl


def test_build_retrieval_training_sets_writes_expected_outputs(tmp_path):
    paths = build_retrieval_training_sets(
        [
            {
                "query_id": "q1",
                "question": "Nguoi lao dong duoc nghi bao nhieu ngay?",
                "positive_context": "Nguoi lao dong duoc nghi 12 ngay.",
                "positive_cids": ["1"],
                "doc_name": "Bo luat Lao dong",
            },
            {
                "query_id": "q2",
                "question": "Dieu kien huong tro cap la gi?",
                "positive_context": "Can du dieu kien theo luat.",
                "positive_cids": ["2"],
                "doc_name": "Bo luat Lao dong",
            },
            {
                "query_id": "q3",
                "question": "Hop dong tam hoan khi nao?",
                "positive_context": "Tam hoan trong mot so truong hop.",
                "positive_cids": ["3"],
                "doc_name": "Bo luat Lao dong",
            },
        ],
        RetrievalBuildConfig(output_dir=str(tmp_path), negatives_per_query=2),
    )
    retriever_records = load_jsonl(paths["retriever_train"])
    reranker_records = load_jsonl(paths["reranker_train"])
    manifest = load_json(paths["manifest"])
    assert len(retriever_records) == 3
    assert len(reranker_records) == 9
    assert len(retriever_records[0]["negatives"]) == 2
    assert manifest["negatives_per_query"] == 2
