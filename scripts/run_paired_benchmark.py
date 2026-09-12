"""Run paired benchmark: Base vs QLoRA on identical samples.

Ensures:
  - Same sample IDs for both models
  - Same prompt template
  - Same decoding (temperature=0, do_sample=False)
  - Same parsing logic
  - Saves raw + parsed + correct for each sample

Usage:
    python scripts/run_paired_benchmark.py --config configs/evaluation/vlegal_tasks.yaml
    python scripts/run_paired_benchmark.py --config configs/evaluation/vlegal_tasks.yaml --tasks article_clause_prediction
    python scripts/run_paired_benchmark.py --config configs/evaluation/vlegal_tasks.yaml --dry-run
"""
from __future__ import annotations

import argparse
import json
import hashlib
import sys
from pathlib import Path

import scripts._bootstrap as _bootstrap  # noqa: F401

try:
    import yaml
except ImportError:
    yaml = None

from src.evaluation.paired_benchmark import (
    EvalSample,
    TaskResult,
    load_paired_samples,
    save_eval_ids,
    save_paired_results,
    build_prompt,
    run_paired_evaluation,
)


def load_config(config_path: Path) -> dict:
    """Load YAML or JSON config."""
    text = config_path.read_text(encoding="utf-8")
    if config_path.suffix in (".yaml", ".yml"):
        if yaml is None:
            raise SystemExit("PyYAML required for YAML config. pip install pyyaml")
        return yaml.safe_load(text)
    return json.loads(text)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run paired benchmark: Base vs QLoRA on identical samples."
    )
    parser.add_argument(
        "--config",
        default="configs/evaluation/vlegal_tasks.yaml",
        help="Task config file (YAML or JSON).",
    )
    parser.add_argument(
        "--tasks",
        nargs="*",
        help="Specific task IDs to run (default: all tasks with data).",
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        default=0,
        help="Max samples per task (0 = all).",
    )
    parser.add_argument(
        "--output-dir",
        default="results/paired_benchmark",
        help="Output directory.",
    )
    parser.add_argument(
        "--save-ids",
        default="configs/evaluation/eval_ids.json",
        help="Path to save/load fixed eval IDs.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Load data and show what would be evaluated without running.",
    )
    parser.add_argument(
        "--base-model",
        default=None,
        help="Override base model path.",
    )
    parser.add_argument(
        "--adapter",
        default=None,
        help="Override adapter path.",
    )
    args = parser.parse_args()

    config = load_config(Path(args.config))
    project = config.get("project", {})
    tasks_config = config.get("tasks", {})

    base_model = args.base_model or project.get("base_model", "Qwen/Qwen2.5-7B-Instruct")
    adapter = args.adapter or project.get("adapter", "")
    inference = project.get("inference", {})

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Determine which tasks to run
    task_ids = args.tasks or list(tasks_config.keys())
    all_samples: list[EvalSample] = []

    print(f"Base model: {base_model}")
    print(f"Adapter: {adapter or '(none)'}")
    print(f"Inference: temp={inference.get('temperature', 0)}, "
          f"max_new_tokens={inference.get('max_new_tokens', 256)}")
    print(f"Tasks: {task_ids}")
    print()

    task_results: list[dict] = []

    for task_id in task_ids:
        if task_id not in tasks_config:
            print(f"WARNING: Task '{task_id}' not in config, skipping.")
            continue

        tc = tasks_config[task_id]
        tc["task_id"] = task_id

        samples = load_paired_samples(tc, max_samples=args.max_samples, seed=args.seed)
        if not samples:
            print(f"  {task_id}: NO DATA (file not found: {tc.get('data_path', '?')})")
            print(f"    -> Create data file and re-run. Skipping.")
            task_results.append({
                "task_id": task_id,
                "status": "no_data",
                "data_path": tc.get("data_path", ""),
            })
            continue

        min_samples = tc.get("min_samples", 100)
        if len(samples) < min_samples:
            print(f"  {task_id}: WARNING - only {len(samples)} samples (min: {min_samples})")

        print(f"  {task_id}: {len(samples)} samples, type={tc.get('task_type')}, "
              f"metric={tc.get('metric')}")

        all_samples.extend(samples)

        task_results.append({
            "task_id": task_id,
            "status": "ready",
            "n": len(samples),
            "task_type": tc.get("task_type"),
            "metric": tc.get("metric"),
            "data_path": tc.get("data_path"),
        })

    # Save eval IDs
    if all_samples:
        ids_path = Path(args.save_ids)
        save_eval_ids(all_samples, ids_path)
        print(f"\nSaved {len(all_samples)} eval IDs to {ids_path}")

    # Summary
    summary = {
        "config": args.config,
        "base_model": base_model,
        "adapter": adapter,
        "inference": inference,
        "total_samples": len(all_samples),
        "tasks": task_results,
    }
    summary_path = output_dir / "benchmark_plan.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nBenchmark plan saved to {summary_path}")

    if args.dry_run:
        print("\n[DRY RUN] Exiting without running inference.")
        return

    # Actually run inference
    print("\n" + "=" * 60)
    print("RUNNING PAIRED INFERENCE")
    print("=" * 60)

    # Lazy import to allow dry-run without GPU
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from peft import PeftModel
    except ImportError:
        print("\nERROR: Missing inference deps. Install requirements-runpod.txt")
        print("Run with --dry-run to see plan without inference.")
        sys.exit(1)

    # Load models once
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
    else:
        print("WARNING: No adapter loaded. QLoRA will use base model.")

    has_qlora = qlora_model_obj is not None and adapter and Path(adapter).exists()

    def generate_fn(sample: EvalSample, tc: dict):
        """Generate from both models on same input."""
        prompt = build_prompt(sample, tc)
        inputs = tokenizer(prompt, return_tensors="pt").to(base_model_obj.device)

        gen_kwargs = {
            "max_new_tokens": inference.get("max_new_tokens", 256),
            "do_sample": inference.get("do_sample", False),
            "temperature": inference.get("temperature", 0),
            "eos_token_id": tokenizer.eos_token_id,
            "pad_token_id": tokenizer.pad_token_id,
        }

        with torch.no_grad():
            base_outputs = base_model_obj.generate(**inputs, **gen_kwargs)
        base_raw = tokenizer.decode(
            base_outputs[0][inputs["input_ids"].shape[-1]:],
            skip_special_tokens=True,
        ).strip()

        if has_qlora:
            with torch.no_grad():
                qlora_outputs = qlora_model_obj.generate(**inputs, **gen_kwargs)
            qlora_raw = tokenizer.decode(
                qlora_outputs[0][inputs["input_ids"].shape[-1]:],
                skip_special_tokens=True,
            ).strip()
        else:
            qlora_raw = base_raw

        return base_raw, qlora_raw

    # Run each task
    all_task_results: list[TaskResult] = []
    for task_id in task_ids:
        if task_id not in tasks_config:
            continue
        tc = tasks_config[task_id]
        tc["task_id"] = task_id
        samples = load_paired_samples(tc, max_samples=args.max_samples, seed=args.seed)
        if not samples:
            continue

        print(f"\nRunning: {task_id} ({len(samples)} samples)...")
        result = run_paired_evaluation(
            samples=samples,
            task_config=tc,
            generate_fn=generate_fn,
            task_id=task_id,
        )
        save_paired_results(result, output_dir)
        all_task_results.append(result)
        print(f"  Base: {result.base_score:.4f}, QLoRA: {result.qlora_score:.4f}, "
              f"Delta: {result.delta:+.4f}")

    # Final summary
    final = {
        "config": args.config,
        "base_model": base_model,
        "adapter": adapter,
        "tasks": [
            {
                "task_id": r.task_id,
                "n": r.n,
                "base_score": r.base_score,
                "qlora_score": r.qlora_score,
                "delta": r.delta,
            }
            for r in all_task_results
        ],
    }
    (output_dir / "benchmark_summary.json").write_text(
        json.dumps(final, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nResults saved to {output_dir}")


if __name__ == "__main__":
    main()
