"""Generate paper-ready tables and figures.

Produces:
  Table 1 — Internal LegalQA (from existing results)
  Table 2 — External VLegal paired benchmark
  Table 3 — Capability transfer (valid mappings only)
  Table 4 — Evidence degradation (8 conditions)
  Table 5 — Evidence sensitivity (AAR, UCR, PPR)

Figures:
  Fig 1 — Internal gain vs External gain
  Fig 2 — Evidence degradation curve (Base vs QLoRA)

Usage:
    python scripts/generate_paper_tables.py --results-dir results
    python scripts/generate_paper_tables.py --results-dir results --format latex
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import scripts._bootstrap as _bootstrap  # noqa: F401

try:
    import yaml
except ImportError:
    yaml = None


def load_json(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def generate_table1_internal(results_dir: Path) -> str:
    """Table 1: Internal LegalQA results (existing pilot)."""
    report_path = results_dir / "paper_experiments.json"
    if not report_path.exists():
        return "\\textbf{Table 1: Internal LegalQA} — Data not available.\n"

    report = load_json(report_path)
    gen = report.get("answer_generation", {})
    retrieved = report.get("retrieved_answer_generation", {})
    prompt_only = report.get("retrieved_prompt_only_generation", {})

    lines = [
        "\\begin{table}[t]",
        "\\centering",
        "\\caption{Internal LegalQA: Qwen2.5-7B-Instruct base vs.~QLoRA-adapted.}",
        "\\label{tab:internal}",
        "\\begin{tabular}{lrrrrr}",
        "\\toprule",
        "Variant & N & Token F1 & ROUGE-L & Citation & Faith. \\\\",
        "\\midrule",
    ]

    if prompt_only:
        lines.append(
            f"Prompt-only (RAG) & {prompt_only.get('samples', 0)} & "
            f"{prompt_only.get('token_f1', 0):.4f} & "
            f"{prompt_only.get('rouge_l', 0):.4f} & "
            f"{prompt_only.get('citation_presence', 0):.3f} & "
            f"{prompt_only.get('faithfulness_score', 0):.4f} \\\\"
        )
    if retrieved:
        lines.append(
            f"\\textbf{{QLoRA (RAG)}} & {retrieved.get('samples', 0)} & "
            f"\\textbf{{{retrieved.get('token_f1', 0):.4f}}} & "
            f"\\textbf{{{retrieved.get('rouge_l', 0):.4f}}} & "
            f"\\textbf{{{retrieved.get('citation_presence', 0):.3f}}} & "
            f"{retrieved.get('faithfulness_score', 0):.4f} \\\\"
        )

    lines.extend([
        "\\bottomrule",
        "\\end{tabular}",
        "\\end{table}",
        "",
    ])
    return "\n".join(lines)


def generate_table2_external(results_dir: Path) -> str:
    """Table 2: External VLegal paired benchmark."""
    paired_dir = results_dir / "paired_benchmark"
    if not paired_dir.exists():
        return "\\textbf{Table 2: External VLegal} — Run run_paired_benchmark.py first.\n"

    stats_path = paired_dir / "statistical_tests.json"
    if not stats_path.exists():
        return "\\textbf{Table 2: External VLegal} — Run run_statistical_tests.py first.\n"

    stats = load_json(stats_path)

    lines = [
        "\\begin{table}[t]",
        "\\centering",
        "\\caption{External VLegal Paired Benchmark. Base vs.~QLoRA on identical samples.}",
        "\\label{tab:external}",
        "\\begin{tabular}{lclcc}",
        "\\toprule",
        "Task & N & Metric & Base & QLoRA & $\\Delta$ (95\\% CI) \\\\",
        "\\midrule",
    ]

    for s in stats:
        task = s.get("task_id", "").replace("_", " ").title()
        n = s.get("n", 0)
        metric = s.get("metric", "acc")
        base = s.get("base_score", 0)
        qlora = s.get("qlora_score", 0)
        delta = s.get("delta", 0)
        ci = s.get("bootstrap", {}).get("delta", {})
        ci_lo = ci.get("ci_low", 0)
        ci_hi = ci.get("ci_high", 0)
        pval = s.get("bootstrap", {}).get("p_value", 1.0)
        sig = "$^*$" if pval < 0.05 else ""

        direction = "\\uparrow" if delta > 0 else "\\downarrow" if delta < 0 else "-"
        lines.append(
            f"{task} & {n} & {metric} & {base:.4f} & {qlora:.4f} & "
            f"{delta:+.4f}{sig} [{ci_lo:+.3f}, {ci_hi:+.3f}] \\\\"
        )

    lines.extend([
        "\\bottomrule",
        "\\end{tabular}",
        "\\vspace{1mm}",
        "\\parbox{0.9\\textwidth}{\\footnotesize $^*$ $p < 0.05$; "
        "CI via paired bootstrap (1000 resamples).}",
        "\\end{table}",
        "",
    ])
    return "\n".join(lines)


def generate_table3_capability(results_dir: Path, config: dict) -> str:
    """Table 3: Capability transfer (valid mappings only)."""
    paired_dir = results_dir / "paired_benchmark"
    stats_path = paired_dir / "statistical_tests.json"
    if not stats_path.exists():
        return "\\textbf{Table 3: Capability Transfer} — No data.\n"

    stats = load_json(stats_path)
    cap_map = config.get("capability_mapping", {})

    # Group tasks by capability
    cap_groups: dict[str, list[dict]] = {}
    for s in stats:
        task_id = s.get("task_id", "")
        # Find capability from config
        for cap_name, cap_info in cap_map.items():
            if cap_info and task_id in cap_info.get("tasks", []):
                vlegal_cap = cap_info.get("vlegal", cap_name)
                if vlegal_cap not in cap_groups:
                    cap_groups[vlegal_cap] = []
                cap_groups[vlegal_cap].append(s)
                break

    lines = [
        "\\begin{table}[t]",
        "\\centering",
        "\\caption{Capability Transfer: Internal $\\to$ External (valid mappings only).}",
        "\\label{tab:capability}",
        "\\begin{tabular}{llccc}",
        "\\toprule",
        "Internal Capability & External Task & Base & QLoRA & $\\Delta$ \\\\",
        "\\midrule",
    ]

    for cap_name, tasks in sorted(cap_groups.items()):
        for i, t in enumerate(tasks):
            task_label = t.get("task_id", "").replace("_", " ").title()
            cap_label = cap_name if i == 0 else ""
            lines.append(
                f"{cap_label} & {task_label} & {t.get('base_score', 0):.4f} & "
                f"{t.get('qlora_score', 0):.4f} & {t.get('delta', 0):+.4f} \\\\"
            )

    lines.extend([
        "\\bottomrule",
        "\\end{tabular}",
        "",
        "\\vspace{1mm}",
        "\\parbox{0.9\\textwidth}{\\footnotesize Only capability-task pairs with clear "
        "semantic alignment are included. Categories without external counterparts "
        "(Ethics/Bias, NER, RE) are marked N/A.}",
        "\\end{table}",
        "",
    ])
    return "\n".join(lines)


def generate_table4_degradation(results_dir: Path) -> str:
    """Table 4: Evidence degradation across 8 conditions."""
    deg_dir = results_dir / "evidence_degradation"
    if not deg_dir.exists():
        return "\\textbf{Table 4: Evidence Degradation} — Run degradation first.\n"

    # Find all task+model degradation results
    json_files = list(deg_dir.glob("*_base_degradation.json"))
    if not json_files:
        return "\\textbf{Table 4: Evidence Degradation} — No results.\n"

    conditions = [
        ("clean", "Clean"),
        ("distractor", "Distractor"),
        ("missing_rule", "Miss. Rule"),
        ("missing_condition", "Miss. Cond."),
        ("missing_exception", "Miss. Exc."),
        ("wrong_similar", "Wrong-Sim."),
        ("empty", "Empty"),
        ("shuffled", "Shuffled"),
    ]

    lines = [
        "\\begin{table}[t]",
        "\\centering",
        "\\caption{Evidence Degradation: Accuracy across 8 conditions.}",
        "\\label{tab:degradation}",
        "\\tiny",
        "\\begin{tabular}{l" + "c" * len(conditions) + "}",
        "\\toprule",
    ]

    header = "Task & " + " & ".join(name for _, name in conditions) + " \\\\"
    lines.append(header)
    lines.append("\\midrule")

    for json_path in sorted(json_files):
        report = load_json(json_path)
        task_id = report.get("task_id", json_path.stem.replace("_base_degradation", ""))
        model_name = report.get("model_name", "base")
        conds = report.get("conditions", {})

        row_parts = [task_id.replace("_", " ").title()]
        for cond_id, _ in conditions:
            acc = conds.get(cond_id, {}).get("accuracy", 0)
            row_parts.append(f"{acc:.3f}")

        lines.append(" & ".join(row_parts) + " \\\\")

    # Add QLoRA rows
    for json_path in sorted(deg_dir.glob("*_qlora_degradation.json")):
        report = load_json(json_path)
        task_id = report.get("task_id", json_path.stem.replace("_qlora_degradation", ""))
        conds = report.get("conditions", {})

        row_parts = [f"\\textbf{{{task_id.replace('_', ' ').title()}}}"]
        for cond_id, _ in conditions:
            acc = conds.get(cond_id, {}).get("accuracy", 0)
            row_parts.append(f"\\textbf{{{acc:.3f}}}")

        lines.append(" & ".join(row_parts) + " \\\\")

    lines.extend([
        "\\bottomrule",
        "\\end{tabular}",
        "\\end{table}",
        "",
    ])
    return "\n".join(lines)


def generate_table5_sensitivity(results_dir: Path) -> str:
    """Table 5: Evidence sensitivity (AAR, UCR, PPR)."""
    deg_dir = results_dir / "evidence_degradation"
    if not deg_dir.exists():
        return "\\textbf{Table 5: Evidence Sensitivity} — No data.\n"

    json_files = list(deg_dir.glob("*_base_degradation.json"))
    if not json_files:
        return "\\textbf{Table 5: Evidence Sensitivity} — No results.\n"

    insufficiency_conditions = ["missing_rule", "missing_condition", "missing_exception", "wrong_similar"]

    lines = [
        "\\begin{table}[t]",
        "\\centering",
        "\\caption{Evidence Sensitivity: AAR, UCR, PPR under evidence insufficiency.}",
        "\\label{tab:sensitivity}",
        "\\begin{tabular}{llccc}",
        "\\toprule",
        "Task & Condition & AAR & UCR & PPR \\\\",
        "\\midrule",
    ]

    for json_path in sorted(json_files):
        report = load_json(json_path)
        task_id = report.get("task_id", "").replace("_", " ").title()
        model_name = report.get("model_name", "")
        conds = report.get("conditions", {})

        first = True
        for cond_id in insufficiency_conditions:
            cond = conds.get(cond_id, {})
            if not cond:
                continue
            task_label = task_id if first else ""
            model_label = f"({model_name})" if first else ""
            lines.append(
                f"{task_label} {model_label} & {cond_id.replace('_', ' ').title()} & "
                f"{cond.get('appropriate_abstention_rate', 0):.3f} & "
                f"{cond.get('unsupported_conclusion_rate', 0):.3f} & "
                f"{cond.get('prediction_persistence_rate', 0):.3f} \\\\"
            )
            first = False

    lines.extend([
        "\\bottomrule",
        "\\end{tabular}",
        "\\vspace{1mm}",
        "\\parbox{0.9\\textwidth}{\\footnotesize AAR: Appropriate Abstention Rate "
        "(higher = better). UCR: Unsupported Conclusion Rate (lower = better). "
        "PPR: Prediction Persistence Rate (high = model ignores evidence).}",
        "\\end{table}",
        "",
    ])
    return "\n".join(lines)


def generate_fig1_internal_vs_external(results_dir: Path) -> str:
    """Figure 1: Internal gain vs External gain (matplotlib code)."""
    return r"""
% Figure 1: Internal gain vs External gain
\begin{figure}[t]
\centering
\begin{tikzpicture}
\begin{axis}[
    width=0.8\textwidth,
    height=6cm,
    xlabel={Internal LegalQA Gain (Token F1)},
    ylabel={External VLegal Gain (Accuracy)},
    xmin=-0.1, xmax=0.15,
    ymin=-0.15, ymax=0.1,
    grid=major,
    legend pos=south west,
]
% Add data points from paired benchmark results
% \addplot[only marks, mark=*, color=blue] coordinates {
%   (internal_delta_1, external_delta_task_1)
%   ...
% };
% \addlegendentry{Task}
\end{axis}
\end{tikzpicture}
\caption{Internal LegalQA gain vs.\ external VLegal gain after QLoRA adaptation. Points below zero on the y-axis indicate specialization--generalization trade-off.}
\label{fig:internal_vs_external}
\end{figure}
"""


def generate_fig2_degradation_curve(results_dir: Path) -> str:
    """Figure 2: Evidence degradation curve."""
    return r"""
% Figure 2: Evidence degradation curve
\begin{figure}[t]
\centering
\begin{tikzpicture}
\begin{axis}[
    width=0.9\textwidth,
    height=7cm,
    xlabel={Evidence Condition},
    ylabel={Accuracy},
    symbolic x coords={Clean, Distractor, Miss. Rule, Miss. Cond., Miss. Exc., Wrong-Sim., Empty, Shuffled},
    xtick=data,
    x tick label style={rotate=45, anchor=east},
    ymin=0, ymax=1,
    grid=major,
    legend pos=north east,
    mark size=2pt,
]
% Base model line
% \addplot[mark=square*, color=red] coordinates { ... };
% \addlegendentry{Base}
% QLoRA model line
% \addplot[mark=triangle*, color=blue] coordinates { ... };
% \addlegendentry{QLoRA}
\end{axis}
\end{tikzpicture}
\caption{Evidence degradation curve: Base vs.\ QLoRA across 8 evidence conditions. A flat QLoRA line suggests reduced evidence sensitivity.}
\label{fig:degradation}
\end{figure}
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate paper tables and figures.")
    parser.add_argument("--results-dir", default="results")
    parser.add_argument("--config", default="configs/evaluation/vlegal_tasks.yaml")
    parser.add_argument("--format", choices=["latex", "markdown"], default="latex")
    parser.add_argument("--output", default=None, help="Output file path.")
    args = parser.parse_args()

    results_dir = Path(args.results_dir)

    # Load config
    config_path = Path(args.config)
    if config_path.exists():
        text = config_path.read_text(encoding="utf-8")
        try:
            import yaml
            config = yaml.safe_load(text)
        except Exception:
            config = json.loads(text)
    else:
        config = {}

    if args.format == "latex":
        parts = [
            "% Auto-generated paper tables and figures",
            "% Run: python scripts/generate_paper_tables.py --results-dir results",
            "",
            "\\usepackage{booktabs}",
            "\\usepackage{graphicx}",
            "\\usepackage{tikz}",
            "\\usepackage{pgfplots}",
            "\\pgfplotsset{compat=1.18}",
            "",
            generate_table1_internal(results_dir),
            generate_table2_external(results_dir),
            generate_table3_capability(results_dir, config),
            generate_table4_degradation(results_dir),
            generate_table5_sensitivity(results_dir),
            generate_fig1_internal_vs_external(results_dir),
            generate_fig2_degradation_curve(results_dir),
        ]
    else:
        parts = [
            "# Paper Tables (Markdown)",
            "",
            "## Table 1: Internal LegalQA",
            "_See results/paper_experiments.json for existing results._",
            "",
            "## Table 2: External VLegal Paired Benchmark",
            "_See results/paired_benchmark/statistical_tests.md_",
            "",
            "## Table 3: Capability Transfer",
            "_See LaTeX output or compute from paired results._",
            "",
            "## Table 4: Evidence Degradation",
            "_See results/evidence_degradation/_",
            "",
            "## Table 5: Evidence Sensitivity",
            "_See results/evidence_degradation/_",
        ]

    content = "\n".join(parts)

    if args.output:
        output_path = Path(args.output)
    else:
        ext = ".tex" if args.format == "latex" else ".md"
        output_path = results_dir / f"paper_tables{ext}"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    print(f"Paper tables saved to {output_path}")


if __name__ == "__main__":
    main()
