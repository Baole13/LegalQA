from src.data.load_thangvip import load_thangvip_qa_records
from src.data.prepare_sft_data import SFTBuildConfig, build_reasoning_target, build_runpod_sft_dataset
from src.utils.io import load_json, load_jsonl


def test_build_reasoning_target_contains_expected_sections():
    text = build_reasoning_target(
        {
            "doc_name": "Bo luat Lao dong",
            "answer": "Nguoi lao dong phai co it nhat 12 thang lam viec.",
        }
    )
    assert "Tra loi:" in text
    assert "Can cu:" in text
    assert "Lap luan:" in text
    assert "12 thang lam viec" in text


def test_build_runpod_sft_dataset_writes_splits(tmp_path):
    paths = build_runpod_sft_dataset(
        [
            {
                "record_id": "1",
                "doc_name": "Bo luat Lao dong",
                "doc_type_name": "Bo luat",
                "article_content": "Noi dung dieu luat.",
                "question": "Cau hoi 1?",
                "answer": "Tra loi 1.",
                "question_type": "application",
                "difficulty": "medium",
            },
            {
                "record_id": "2",
                "doc_name": "Bo luat Lao dong",
                "doc_type_name": "Bo luat",
                "article_content": "Noi dung dieu luat 2.",
                "question": "Cau hoi 2?",
                "answer": "Tra loi 2.",
                "question_type": "analytical",
                "difficulty": "hard",
            },
            {
                "record_id": "3",
                "doc_name": "Bo luat Lao dong",
                "doc_type_name": "Bo luat",
                "article_content": "Noi dung dieu luat 3.",
                "question": "Cau hoi 3?",
                "answer": "Tra loi 3.",
                "question_type": "factual",
                "difficulty": "easy",
            },
        ],
        config=SFTBuildConfig(output_dir=str(tmp_path), reasoning_ratio=1.0),
    )
    train_records = load_jsonl(paths["train"])
    manifest = load_json(paths["manifest"])
    assert train_records
    assert manifest["total_records"] == 3
    assert train_records[0]["messages"][0]["role"] == "system"


def test_load_thangvip_qa_records_flattens_generated_pairs(tmp_path):
    import pandas as pd

    dataset_path = tmp_path / "sample.parquet"
    pd.DataFrame(
        [
            {
                "doc_name": "Bo luat Lao dong",
                "doc_type_name": "Bo luat",
                "article_content": "Noi dung van ban.",
                "generated_qa_pairs": '[{"question":"Ai duoc huong?","answer":"Nguoi lao dong."}]',
            }
        ]
    ).to_parquet(dataset_path)
    records = load_thangvip_qa_records(dataset_path)
    assert len(records) == 1
    assert records[0]["question"] == "Ai duoc huong?"
