from __future__ import annotations

import _bootstrap

from src.training.qwen_sft import train_qwen_sft


def main() -> None:
    output_dir = train_qwen_sft(config_path="configs/training/runpod.qwen2_5_7b_qlora.json")
    print(f"Saved Qwen SFT model to {output_dir}")


if __name__ == "__main__":
    main()
