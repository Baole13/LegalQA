"""Run evidence degradation evaluation.

For each task, runs both Base and QLoRA through 8 evidence conditions:
  C1 Clean, C2 Distractor, C3 Missing Rule, C4 Missing Condition,
  C5 Missing Exception, C6 Wrong-Similar, C7 Empty, C8 Shuffled

Computes:
  - Accuracy/F1 per condition
  - Noise Robustness Drop
  - Appropriate Abstention Rate (AAR)
  - Unsupported Conclusion Rate (UCR)
  - Prediction Persistence Rate (PPR)

Usage:
    python scripts/run_evidence_degradation.py --config configs/evaluation/vlegal_tasks.yaml
    python scripts/run_evidence_degradation.py --config configs/evaluation/vlegal_tasks.yaml --tasks multi_hop_reasoning
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import scripts._bootstrap as _bootstrap  # noqa: F401

try:
    import yaml
except ImportError:
    yaml = None

from src.evaluation.paired_benchmark import (
    EvalSample,
    load_paired_samples,
    build_prompt,
)
from src.evaluation.evidence_degradation import (
    run_degradation_single_model,
    save_degradation_report,
    compute_noise_robustness_drop,
)
from src.evaluation.paper_metrics import (
    appropriate_abstention_rate,
    unsupported_conclusion_rate,
    prediction_persistence_rate,
)


def load_config(config_path: Path) -> dict:
    text = config_path.read_text(encoding="utf-8")
    if config_path.suffix in (".yaml", ".yml"):
        if yaml is None:
            raise SystemExit("PyYAML required. pip install pyyaml")
        return yaml.safe_load(text)
    return json.loads(text)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run evidence degradation evaluation.")
    parser.add_argument("--config", default="configs/evaluation/vlegal_tasks.yaml")
    parser.add_argument("--tasks", nargs="*", help="Task IDs to evaluate.")
    parser.add_argument("--max-samples", type=int, default=200,
                        help="Max samples per task (recommended: 200-300).")
    parser.add_argument("--output-dir", default="results/evidence_degradation")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--base-model", default=None)
    parser.add_argument("--adapter", default=None)
    args = parser.parse_args()

    config = load_config(Path(args.config))
    project = config.get("project", {})
    tasks_config = config.get("tasks", {})

    base_model = args.base_model or project.get("base_model", "Qwen/Qwen2.5-7B-Instruct")
    adapter = args.adapter or project.get("adapter", "")
    inference = project.get("inference", {})

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    task_ids = args.tasks or list(tasks_config.keys())

    print(f"Base model: {base_model}")
    print(f"Adapter: {adapter or '(none)'}")
    print(f"Max samples: {args.max_samples}")
    print(f"Tasks: {task_ids}")

    if args.dry_run:
        print("\n[DRY RUN] Checking data availability...")
        for task_id in task_ids:
            tc = tasks_config.get(task_id, {})
            data_path = tc.get("data_path", "")
            exists = Path(data_path).exists() if data_path else False
            print(f"  {task_id}: {'OK' if exists else 'NO DATA'} ({data_path})")
        return

    # Load models
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from peft import PeftModel
    except ImportError:
        print("ERROR: Missing inference deps.")
        sys.exit(1)

    print(f"\nLoading base model: {base_model}")
    tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=False)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    base_model_obj = AutoModelForCausalLM.from_pretrained(
        base_model,
        dtype=getattr(torch, "bfloat16", torch.float16),
        device_map="auto",
        trust_remote_code=False,
    )
    base_model_obj.eval()

    qlora_model_obj = None
    if adapter and Path(adapter).exists():
        print(f"Loading QLoRA adapter: {adapter}")
        qlora_model_obj = PeftModel.from_pretrained(base_model_obj, adapter)
        qlora_model_obj.eval()

    gen_kwargs = {
        "max_new_tokens": inference.get("max_new_tokens", 256),
        "do_sample": inference.get("do_sample", False),
        "temperature": inference.get("temperature", 0),
        "eos_token_id": tokenizer.eos_token_id,
        "pad_token_id": tokenizer.pad_token_id,
    }

    def make_generate_fn(model):
        def generate_fn(sample: EvalSample, evidence: str) -> str:
            modified_sample = EvalSample(
                sample_id=sample.sample_id,
                task_id=sample.task_id,
                question=sample.question,
                evidence=evidence,
                gold=sample.gold,
                choices=sample.choices,
                metadata=sample.metadata,
            )
            tc = {"task_type": sample.metadata.get("task_type", "mcq")}
            prompt = build_prompt(modified_sample, tc)
            inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
            with torch.no_grad():
                outputs = model.generate(**inputs, **gen_kwargs)
            return tokenizer.decode(
                outputs[0][inputs["input_ids"].shape[-1]:],
                skip_special_tokens=True,
            ).strip()
        return generate_fn

    # Run degradation for both models
    for model_name, model_obj in [
        ("base", base_model_obj),
        ("qlora", qlora_model_obj or base_model_obj),
    ]:
        print(f"\n{'='*60}")
        print(f"Running degradation: {model_name}")
        print(f"{'='*60}")

        generate_fn = make_generate_fn(model_obj)

        for task_id in task_ids:
            tc = tasks_config.get(task_id, {})
            tc["task_id"] = task_id
            samples = load_paired_samples(tc, max_samples=args.max_samples, seed=args.seed)
            if not samples:
                print(f"  {task_id}: NO DATA, skipping")
                continue

            print(f"\n  {task_id} ({len(samples)} samples)...")
            report = run_degradation_single_model(
                samples=samples,
                task_config=tc,
                generate_fn=generate_fn,
                model_name=model_name,
                task_id=task_id,
                seed=args.seed,
            )
            save_degradation_report(report, output_dir)

            # Print summary
            clean = report.conditions.get("clean")
            distractor = report.conditions.get("distractor")
            empty = report.conditions.get("empty")
            shuffled = report.conditions.get("shuffled")

            nrd = compute_noise_robustness_drop(
                clean.accuracy if clean else 0,
                distractor.accuracy if distractor else 0,
            )
            print(f"    Clean: {clean.accuracy:.4f}" if clean else "    Clean: N/A")
            print(f"    Distractor: {distractor.accuracy:.4f}" if distractor else "")
            print(f"    Noise Robustness Drop: {nrd:.4f}")
            print(f"    Empty: {empty.accuracy:.4f}" if empty else "")
            print(f"    Shuffled: {shuffled.accuracy:.4f}" if shuffled else "")

            # AAR/UCR/PPR for insufficiency conditions
            for cond_id in ["missing_rule", "missing_condition", "missing_exception", "wrong_similar"]:
                cond = report.conditions.get(cond_id)
                if cond:
                    print(f"    {cond_id}: acc={cond.accuracy:.4f} "
                          f"AAR={cond.appropriate_abstention_rate:.4f} "
                          f"UCR={cond.unsupported_conclusion_rate:.4f} "
                          f"PPR={cond.prediction_persistence_rate:.4f}")

    print(f"\nResults saved to {output_dir}")


if __name__ == "__main__":
    main()
