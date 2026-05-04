from __future__ import annotations

import json
import re

from src.utils.io import load_json


class QwenReasoner:
    def __init__(self, config_path: str = "configs/serving/llm.qwen.json"):
        self.config_path = config_path
        self.config = load_json(config_path)
        self.enabled = bool(self.config.get("enabled", True))
        self.model_name = self.config.get("model_name", "Qwen/Qwen2.5-3B-Instruct")
        self._generator = None
        self.loaded = False
        self.load_error: str | None = None

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
        try:
            from transformers import pipeline
        except ImportError as exc:  # pragma: no cover
            self.load_error = f"transformers_not_installed: {exc}"
            return

        try:
            self._generator = pipeline(
                "text-generation",
                model=self.model_name,
                device_map=self.config.get("device_map", "auto"),
                trust_remote_code=bool(self.config.get("trust_remote_code", False)),
            )
            self.loaded = True
        except Exception as exc:  # pragma: no cover
            self.load_error = str(exc)

    def generate(self, prompt: str) -> dict | None:
        if not self.is_available():
            return None
        try:
            outputs = self._generator(
                prompt,
                max_new_tokens=int(self.config.get("max_new_tokens", 384)),
                temperature=float(self.config.get("temperature", 0.1)),
                top_p=float(self.config.get("top_p", 0.9)),
                do_sample=True,
                return_full_text=False,
            )
            text = outputs[0]["generated_text"].strip()
            return self._parse_json(text)
        except Exception:  # pragma: no cover
            return None

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
