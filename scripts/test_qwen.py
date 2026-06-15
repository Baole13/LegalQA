from __future__ import annotations

import argparse
from pathlib import Path

import _bootstrap

REQUIRED_SECTIONS = (
    "Can cu phap ly:",
    "Dieu kien phap ly lien quan:",
    "Ap dung vao tinh huong:",
    "Ket luan:",
    "Thong tin con thieu:",
)


DEFAULT_QUESTION = "Theo quy dinh phap luat hien hanh, nguoi lao dong duoc nghi hang nam bao nhieu ngay lam viec?"
DEFAULT_CONTEXT = (
    "Dieu 113. Nghi hang nam\n"
    "1. Nguoi lao dong co du 12 thang lam viec cho mot nguoi su dung lao dong thi duoc nghi hang nam, huong nguyen luong theo hop dong lao dong 12 ngay lam viec."
)


def build_prompt(question: str, context: str, instruction: str) -> list[dict]:
    return [
        {"role": "system", "content": instruction.strip()},
        {
            "role": "user",
            "content": (
                "Van ban phap ly:\n"
                f"{context.strip()}\n\n"
                "Cau hoi:\n"
                f"{question.strip()}\n\n"
                "Yeu cau:\n"
                "Tra loi theo dung 5 phan bat buoc va chi dua tren van ban duoc cung cap.\n"
                "Neu khong du can cu thi phai noi ro khong du can cu.\n"
                "Tra loi theo format:\n"
                "Can cu phap ly:\n"
                "- ...\n\n"
                "Dieu kien phap ly lien quan:\n"
                "- ...\n\n"
                "Ap dung vao tinh huong:\n"
                "- ...\n\n"
                "Ket luan:\n"
                "- ...\n\n"
                "Thong tin con thieu:\n"
                "- ...\n\n"
                "Luu y:\n"
                "- Moi can cu can co citation ro rang neu co the.\n"
                "- Khong duoc dua them luat ngoai context.\n"
            ).strip(),
        },
    ]


def render_prompt(tokenizer, messages: list[dict]) -> str:
    if hasattr(tokenizer, "apply_chat_template"):
        return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    return "\n\n".join(f"{msg['role'].capitalize()}: {msg['content']}" for msg in messages) + "\n\nAssistant:"


def main() -> None:
    parser = argparse.ArgumentParser(description="Quick local test for the fine-tuned Qwen adapter.")
    parser.add_argument(
        "--base-model",
        default="Qwen/Qwen2.5-7B-Instruct",
        help="Base model name or local path.",
    )
    parser.add_argument(
        "--adapter",
        default="models/qwen2.5-7b-legalqa-qlora",
        help="LoRA adapter directory saved by training.",
    )
    parser.add_argument(
        "--question",
        default=DEFAULT_QUESTION,
        help="Question to test.",
    )
    parser.add_argument(
        "--context",
        default=DEFAULT_CONTEXT,
        help="Legal context to feed into the model.",
    )
    parser.add_argument(
        "--max-new-tokens",
        type=int,
        default=256,
        help="Generation length.",
    )
    args = parser.parse_args()

    try:
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("Missing inference dependencies. Install requirements-runpod.txt first.") from exc

    adapter_path = Path(args.adapter)
    if not adapter_path.exists():
        raise SystemExit(
            f"Adapter path not found: {adapter_path}. "
            "Run training first or point --adapter to the saved LoRA directory."
        )

    tokenizer = AutoTokenizer.from_pretrained(args.base_model, trust_remote_code=False)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        torch_dtype=getattr(torch, "bfloat16", torch.float16),
        device_map="auto",
        trust_remote_code=False,
    )
    model = PeftModel.from_pretrained(model, str(adapter_path))
    model.eval()

    instruction = (
        "Ban la tro ly phap ly tieng Viet. "
        "Chi duoc tra loi dua tren van ban duoc cung cap. "
        "Neu khong du can cu thi phai noi ro khong du can cu. "
        "Tra loi dung format da yeu cau."
    )
    messages = build_prompt(args.question, args.context, instruction)
    prompt = render_prompt(tokenizer, messages)

    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=int(args.max_new_tokens),
            do_sample=False,
            eos_token_id=tokenizer.eos_token_id,
            pad_token_id=tokenizer.pad_token_id,
        )

    generated = outputs[0][inputs["input_ids"].shape[-1] :]
    text = tokenizer.decode(generated, skip_special_tokens=True).strip()
    structure_score = _structure_score(text)
    citation_score = 1.0 if _has_citation(text) else 0.0
    reasoning_score = _reasoning_score(text)
    print("\n=== QUESTION ===")
    print(args.question)
    print("\n=== CONTEXT ===")
    print(args.context)
    print("\n=== ANSWER ===")
    print(text or "[empty output]")
    print("\n=== QUICK CHECK ===")
    print(f"structure_score: {structure_score:.2f}")
    print(f"citation_score: {citation_score:.2f}")
    print(f"reasoning_score: {reasoning_score:.2f}")


def _structure_score(text: str) -> float:
    normalized = text.lower()
    hits = sum(1 for section in REQUIRED_SECTIONS if section.lower() in normalized)
    return hits / len(REQUIRED_SECTIONS)


def _has_citation(text: str) -> bool:
    normalized = text.lower()
    return any(marker in normalized for marker in ("dieu ", "khoan ", "[", "can cu phap ly"))


def _reasoning_score(text: str) -> float:
    normalized = text.lower()
    markers = ("do do", "vi vay", "theo do", "tu do", "suy ra", "neu khong du can cu")
    hits = sum(1 for marker in markers if marker in normalized)
    return hits / len(markers)


if __name__ == "__main__":
    main()
