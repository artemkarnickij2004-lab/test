"""Клиент генерации ответа поверх любого OpenAI-совместимого API.

Без ключа приложение не падает, а переходит в retrieval-only режим
(экстрактивный ответ из найденных фрагментов) — см. pipeline.py.
Это позволяет демонстрировать проект и без платного API.
"""
from __future__ import annotations

from .retrieval import Hit

SYSTEM_PROMPT = """Ты — корпоративный ассистент, отвечающий строго на основе контекста.

Правила:
- Используй ТОЛЬКО информацию из блоков контекста ниже; ничего не выдумывай.
- После каждого факта ставь ссылку на источник: [1], [2] и т.д.
- Один и тот же источник можно цитировать несколько раз.
- Если контекста не хватает для точного ответа — честно скажи об этом
  и предложи, как переформулировать вопрос.
- Отвечай на языке вопроса, кратко и по делу; списки уместны."""


def build_user_prompt(question: str, hits: list[Hit]) -> str:
    blocks = [f"[{i}] (Документ: «{h.chunk.doc_title}»)\n{h.chunk.text}" for i, h in enumerate(hits, 1)]
    context = "\n\n".join(blocks)
    return f"Контекст:\n{context}\n\nВопрос: {question}"


class LLMClient:
    def __init__(self, api_key: str, base_url: str, model: str, temperature: float = 0.2):
        self.model = model
        self.temperature = temperature
        self.enabled = bool(api_key.strip())
        self._client = None
        if self.enabled:
            from openai import OpenAI

            self._client = OpenAI(api_key=api_key, base_url=base_url)

    def generate(self, question: str, hits: list[Hit]) -> str:
        assert self._client is not None, "LLMClient.generate() вызван без API-ключа"
        response = self._client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(question, hits)},
            ],
        )
        return (response.choices[0].message.content or "").strip()
