from __future__ import annotations

import json
import re
from pathlib import Path

from src.utils.io import load_json


class QwenReasoner:
    def __init__(self, config_path: str = "configs/serving/llm.qwen.json", adapter_path: str = ""):
        self.config_path = config_path
        self.config = load_json(config_path)
        self.enabled = bool(self.config.get("enabled", True))
        # Keep a stable attribute for health/debug endpoints after simplifying
        # the runtime to a single local Transformers backend on RunPod.
        self.backend = str(self.config.get("backend", "transformers"))
        self.model_name = self.config.get("model_name", "Qwen/Qwen2.5-3B-Instruct")
        self.adapter_path = str(adapter_path or self.config.get("adapter_path", "")).strip()
        self.local_files_only = bool(self.config.get("local_files_only", True))
        self._generator = None
        self.loaded = False
        self.load_error: str | None = None
        self.last_raw_text: str = ""
        self.last_parsed: dict | None = None

    def is_available(self) -> bool:
        if not self.enabled:
            return False
        if self.loaded:
            return True
        self._lazy_load()
        return self.loaded

    def _lazy_load(self) -> None:
        if self.loaded or self.load_error is not None:
            return
        self._load_transformers_backend()

    def _load_transformers_backend(self) -> None:
        model_path = Path(self.model_name)
        adapter_path = Path(self.adapter_path) if self.adapter_path else None
        if self.local_files_only and not model_path.exists():
            self.load_error = "local_model_not_found"
            return

        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
            from peft import PeftModel
        except ImportError as exc:  # pragma: no cover
            self.load_error = f"transformers_or_peft_not_installed: {exc}"
            return

        try:
            if adapter_path and adapter_path.exists():
                tokenizer = AutoTokenizer.from_pretrained(
                    self.model_name,
                    trust_remote_code=bool(self.config.get("trust_remote_code", False)),
                    local_files_only=self.local_files_only,
                )
                if tokenizer.pad_token is None:
                    tokenizer.pad_token = tokenizer.eos_token
                model = AutoModelForCausalLM.from_pretrained(
                    self.model_name,
                    device_map=self.config.get("device_map", "auto"),
                    trust_remote_code=bool(self.config.get("trust_remote_code", False)),
                    local_files_only=self.local_files_only,
                    torch_dtype=getattr(torch, str(self.config.get("torch_dtype", "bfloat16"))),
                )
                model = PeftModel.from_pretrained(model, str(adapter_path))
                self._generator = pipeline(
                    "text-generation",
                    model=model,
                    tokenizer=tokenizer,
                    trust_remote_code=bool(self.config.get("trust_remote_code", False)),
                )
            else:
                self._generator = pipeline(
                    "text-generation",
                    model=self.model_name,
                    device_map=self.config.get("device_map", "auto"),
                    trust_remote_code=bool(self.config.get("trust_remote_code", False)),
                    local_files_only=self.local_files_only,
                )
            self.loaded = True
        except Exception as exc:  # pragma: no cover
            self.load_error = str(exc)

    def generate(self, prompt: str) -> dict | None:
        if not self.is_available():
            return None
        try:
            text = self._generate_transformers(prompt)
            self.last_raw_text = text
            self.last_parsed = self._parse_json(text)
            return self.last_parsed
        except Exception as exc:  # pragma: no cover
            self.load_error = str(exc)
            return None

    def _generate_transformers(self, prompt: str) -> str:
        tokenizer = getattr(self._generator, "tokenizer", None)
        model = getattr(self._generator, "model", None)
        if tokenizer is not None and model is not None and hasattr(tokenizer, "apply_chat_template"):
            messages = [
                {
                    "role": "system",
                    "content": "Ban la tro ly phap ly tieng Viet. Tra ve dung mot JSON hop le, khong markdown, khong lap lai prompt.",
                },
                {"role": "user", "content": prompt},
            ]
            encoded = tokenizer.apply_chat_template(
                messages,
                tokenize=True,
                add_generation_prompt=True,
                return_tensors="pt",
                return_dict=True,
            )
            encoded = {key: value.to(model.device) for key, value in encoded.items()}
            input_ids = encoded["input_ids"]
            generation_kwargs = {
                "max_new_tokens": int(self.config.get("max_new_tokens", 384)),
                "min_new_tokens": int(self.config.get("min_new_tokens", 8)),
                "temperature": float(self.config.get("temperature", 0.1)),
                "top_p": float(self.config.get("top_p", 0.9)),
                "do_sample": bool(self.config.get("do_sample", False)),
                "eos_token_id": tokenizer.eos_token_id,
                "pad_token_id": tokenizer.pad_token_id or tokenizer.eos_token_id,
            }
            outputs = model.generate(**encoded, **generation_kwargs)
            generated = outputs[0][input_ids.shape[-1] :]
            return tokenizer.decode(generated, skip_special_tokens=True).strip()

        outputs = self._generator(
            prompt,
            max_new_tokens=int(self.config.get("max_new_tokens", 384)),
            temperature=float(self.config.get("temperature", 0.1)),
            top_p=float(self.config.get("top_p", 0.9)),
            do_sample=bool(self.config.get("do_sample", False)),
            min_new_tokens=int(self.config.get("min_new_tokens", 8)),
            return_full_text=False,
        )
        return outputs[0]["generated_text"].strip()


    def _parse_json(self, text: str) -> dict | None:
        if not text:
            return None
        try:
            return json.loads(text)
        except Exception:
            pass

        fenced = re.search(r"```json\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
        if fenced:
            try:
                return json.loads(fenced.group(1))
            except Exception:
                return None

        raw = re.search(r"(\{.*\})", text, flags=re.DOTALL)
        if raw:
            try:
                return json.loads(raw.group(1))
            except Exception:
                return None
        return None
