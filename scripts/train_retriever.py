from __future__ import annotations

import math
from pathlib import Path

from src.training.data import load_json_config, load_training_records


def main() -> None:
    try:
        from sentence_transformers import InputExample, SentenceTransformer, losses
        from torch.utils.data import DataLoader
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "Missing training dependencies. Install requirements-runpod.txt before running this script."
        ) from exc

    config = load_json_config("configs/training/retriever.train.json")
    train_records = load_training_records(config["train_path"], max_samples=int(config.get("max_samples", 0)))
    if not train_records:
        raise SystemExit("No retriever training data found. Run scripts/prepare_training_data.py first.")

    train_examples = []
    for record in train_records:
        query = record["query"]
        positive = record["positive"]
        negatives = record.get("negatives", [])
        if not negatives:
            continue
        for negative in negatives:
            train_examples.append(InputExample(texts=[query, positive, negative]))

    if not train_examples:
        raise SystemExit("Retriever training examples are empty after processing negatives.")

    model = SentenceTransformer(config["model_name"])
    train_dataloader = DataLoader(
        train_examples,
        shuffle=True,
        batch_size=int(config.get("batch_size", 16)),
    )
    train_loss = losses.TripletLoss(model=model)
    warmup_steps = math.ceil(
        len(train_dataloader) * int(config.get("epochs", 2)) * float(config.get("warmup_ratio", 0.1))
    )

    output_dir = Path(config["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    model.fit(
        train_objectives=[(train_dataloader, train_loss)],
        epochs=int(config.get("epochs", 2)),
        warmup_steps=warmup_steps,
        optimizer_params={"lr": float(config.get("learning_rate", 2e-5))},
        output_path=str(output_dir),
        use_amp=bool(config.get("use_amp", True)),
        show_progress_bar=True,
    )
    print(f"Saved retriever model to {output_dir}")


if __name__ == "__main__":
    main()
