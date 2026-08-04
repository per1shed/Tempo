from __future__ import annotations

import asyncio

from app.utils.logging import get_logger

logger = get_logger(__name__)

GEMINI_TIMEOUT_SEC = 20.0


class GeminiService:
    """Ротация Gemini API keys — одноразовые генерации текста."""

    def __init__(self, keys: list[str], model: str) -> None:
        self.keys = keys
        self.model = model
        self._rr = 0

    @property
    def available(self) -> bool:
        return bool(self.keys)

    async def generate_text(
        self,
        *,
        prompt: str,
        system: str = "Ты краткий помощник. Отвечай по-русски.",
        timeout: float = GEMINI_TIMEOUT_SEC,
        max_attempts: int | None = None,
        temperature: float = 0.9,
    ) -> str:
        if not self.keys:
            return ""
        from google import genai

        n = len(self.keys)
        attempts = min(max_attempts or n, n)
        for attempt in range(attempts):
            idx = (self._rr + attempt) % n
            key = self.keys[idx]
            try:
                client = genai.Client(api_key=key)
                response = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=self.model,
                        contents=prompt,
                        config={
                            "system_instruction": system,
                            "temperature": temperature,
                        },
                    ),
                    timeout=timeout,
                )
                self._rr = (idx + 1) % n
                return (response.text or "").strip()
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "gemini_gen_failed",
                    key_index=idx,
                    error=repr(exc),
                )
        return ""
