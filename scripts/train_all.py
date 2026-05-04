from __future__ import annotations

import subprocess
import sys


def run_step(args: list[str]) -> None:
    print(f"Running: {' '.join(args)}")
    completed = subprocess.run(args, check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def main() -> None:
    run_step([sys.executable, "scripts/prepare_training_data.py"])
    run_step([sys.executable, "scripts/train_retriever.py"])
    run_step([sys.executable, "scripts/train_reranker.py"])


if __name__ == "__main__":
    main()
