from __future__ import annotations

from pathlib import Path

import _bootstrap

from src.data import load_thangvip as thangvip_loader
from src.data.load_yuitc import load_yuitc_retrieval_records
from src.training.data import load_json_config
from src.training.raft import RaftBuildConfig, build_raft_records_from_retrieval_records

try:
    from src.data.prepare_retrieval_data import RetrievalBuildConfig, build_retrieval_training_sets
except ModuleNotFoundError:
    from src.data.prepare_retrieval import RetrievalBuildConfig, build_retrieval_training_sets

try:
    from src.data.prepare_sft_data import SFTBuildConfig, build_runpod_sft_dataset
except ModuleNotFoundError:
    from src.data.prepare_sft import SFTBuildConfig, build_runpod_sft_dataset


def main() -> None:
    thangvip_config = load_json_config("configs/datasets/thangvip.json")
    yuitc_config = load_json_config("configs/datasets/yuitc.json")
    sft_config = load_json_config("configs/training/runpod.qwen2_5_7b_qlora.json")

    thangvip_path = _resolve_dataset_path(Path(thangvip_config["source_path"]))
    if not thangvip_path.exists():
        raise SystemExit(f"Missing thangvip dataset: {thangvip_path}")

    load_thangvip_records = getattr(thangvip_loader, "load_thangvip_qa_records", None)
    if load_thangvip_records is None:
        load_thangvip_records = getattr(thangvip_loader, "load_thangvip_records", None)
    if load_thangvip_records is None:
        available = sorted(name for name in dir(thangvip_loader) if name.startswith("load_"))
        raise SystemExit(
            "src.data.load_thangvip does not expose a supported loader. "
            f"Available load_* symbols: {available}"
        )

    thangvip_records = load_thangvip_records(thangvip_path)
    sft_paths = build_runpod_sft_dataset(
        thangvip_records,
        config=SFTBuildConfig(
            output_dir=str(sft_config.get("prepared_dataset_dir", "data/processed/thangvip_legalqa")),
            train_ratio=float(thangvip_config.get("train_ratio", 0.9)),
            val_ratio=float(thangvip_config.get("val_ratio", 0.05)),
            random_seed=int(thangvip_config.get("random_seed", 42)),
            reasoning_ratio=float(thangvip_config.get("reasoning_ratio", 0.5)),
            max_samples=int(thangvip_config.get("max_samples", 0)),
            instruction=str(sft_config.get("instruction_template", "")),
        ),
    )

    print(f"Prepared thangvip SFT dataset: {len(thangvip_records)} flattened QA pairs")
    print(f"Saved train split: {sft_paths['train']}")
    print(f"Saved val split: {sft_paths['val']}")
    print(f"Saved test split: {sft_paths['test']}")

    yuitc_path = Path(yuitc_config["source_path"])
    if not yuitc_path.exists():
        raise SystemExit(f"Missing YuITC dataset: {yuitc_path}")

    yuitc_records = load_yuitc_retrieval_records(yuitc_path)
    retrieval_paths = build_retrieval_training_sets(
        yuitc_records,
        config=RetrievalBuildConfig(
            output_dir=str(yuitc_config.get("output_dir", "data/aligned")),
            negatives_per_query=int(yuitc_config.get("negatives_per_query", 3)),
            random_seed=int(yuitc_config.get("random_seed", 42)),
            max_samples=int(yuitc_config.get("max_samples", 0)),
        ),
    )
    print(f"Prepared YuITC retrieval pairs: {len(yuitc_records)}")
    print(f"Saved retrieval pairs: {retrieval_paths['retrieval_pairs']}")
    print(f"Saved retriever train: {retrieval_paths['retriever_train']}")
    print(f"Saved reranker train: {retrieval_paths['reranker_train']}")

    raft_records = build_raft_records_from_retrieval_records(
        yuitc_records,
        config=RaftBuildConfig(
            positive_ratio=float(yuitc_config.get("raft_positive_ratio", 0.8)),
            contexts_per_sample=int(yuitc_config.get("raft_contexts_per_sample", 4)),
            distractors_per_positive=int(yuitc_config.get("raft_distractors_per_positive", 2)),
            output_path=str(yuitc_config.get("raft_output_path", "data/aligned/raft_sft.jsonl")),
        ),
    )
    print(f"Saved YuITC RAFT SFT records: {len(raft_records)}")


def _resolve_dataset_path(path: Path) -> Path:
    if path.exists():
        return path

    candidates = [path]
    if path.name == "train.parquet":
        candidates.append(path.with_name("train-00000-of-00001.parquet"))
    if path.name == "train-00000-of-00001.parquet":
        candidates.append(path.with_name("train.parquet"))

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return path


if __name__ == "__main__":
    main()
