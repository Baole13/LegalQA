from __future__ import annotations

import argparse
import math
from pathlib import Path

import _bootstrap 

from src.training.data import load_json_config, load_training_records


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the LegalQA cross-encoder reranker.")
    parser.add_argument("--config", default="configs/training/reranker.train.json", help="Training config JSON path.")
    parser.add_argument("--max-samples", type=int, default=None, help="Override max training records; 0 means all records.")
    parser.add_argument("--epochs", type=int, default=None, help="Override number of training epochs.")
    parser.add_argument("--output-dir", default=None, help="Override output model directory.")
    parser.add_argument("--batch-size", type=int, default=None, help="Override train batch size.")
    parser.add_argument("--no-progress", action="store_true", help="Disable the tqdm progress bar for long non-interactive runs.")
    args = parser.parse_args()

    try:
        from sentence_transformers.cross_encoder import CrossEncoder
        from sentence_transformers.readers import InputExample
        from torch.utils.data import DataLoader
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "Missing training dependencies. Install requirements-runpod.txt before running this script."
        ) from exc

    config = load_json_config(args.config)
    if args.max_samples is not None:
        config["max_samples"] = args.max_samples
    if args.epochs is not None:
        config["epochs"] = args.epochs
    if args.output_dir is not None:
        config["output_dir"] = args.output_dir
    if args.batch_size is not None:
        config["batch_size"] = args.batch_size

    train_records = load_training_records(config["train_path"], max_samples=int(config.get("max_samples", 0)))
    if not train_records:
        raise SystemExit("No reranker training data found. Run scripts/prepare_training_data.py first.")

    train_examples = [
        InputExample(texts=[record["query"], record["passage"]], label=float(record["label"]))
        for record in train_records
        if record.get("query") and record.get("passage") is not None
    ]
    if not train_examples:
        raise SystemExit("Reranker training examples are empty.")

    model = CrossEncoder(config["model_name"], num_labels=1, max_length=512)
    train_dataloader = DataLoader(
        train_examples,
        shuffle=True,
        batch_size=int(config.get("batch_size", 16)),
    )
    warmup_steps = math.ceil(
        len(train_dataloader) * int(config.get("epochs", 2)) * float(config.get("warmup_ratio", 0.1))
    )

    output_dir = Path(config["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    model.fit(
        train_dataloader=train_dataloader,
        epochs=int(config.get("epochs", 2)),
        warmup_steps=warmup_steps,
        optimizer_params={"lr": float(config.get("learning_rate", 2e-5))},
        output_path=str(output_dir),
        use_amp=bool(config.get("use_amp", True)),
        show_progress_bar=not args.no_progress,
    )
    model.save(str(output_dir))
    print(f"Saved reranker model to {output_dir}")


if __name__ == "__main__":
    main()
