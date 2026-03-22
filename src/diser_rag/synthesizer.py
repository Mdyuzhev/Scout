"""Diser RAG — synthesizer: search + Anthropic API -> academic answer."""

import anthropic
from loguru import logger

from . import config
from .searcher import Searcher

SYSTEM_PROMPT = """Ты — аналитик диссертационного исследования. Отвечай строго на основе
предоставленного контекста из исследовательских брифов. Язык ответа: русский.
Стиль: академическая проза, пригодная для включения в диссертацию.
Каждое утверждение подкреплять ссылкой в формате [SW2-004].
Если в контексте нет ответа — честно сообщи об этом.
Не добавляй информацию из общих знаний."""


def synthesize(
    query: str,
    searcher: Searcher,
    domain: str | None = None,
    swarm: str | None = None,
) -> dict:
    """Search + LLM synthesis."""
    results = searcher.search(query, domain=domain, swarm=swarm)

    if not results:
        return {
            "answer": "В проиндексированных материалах не найдено релевантных данных по данному запросу.",
            "sources": [],
        }

    context_parts = []
    sources = []
    seen_briefs = set()
    for r in results:
        context_parts.append(
            f"[{r.brief_id}] ({r.swarm}, {r.topic}):\n{r.text[:2000]}"
        )
        if r.brief_id not in seen_briefs:
            seen_briefs.add(r.brief_id)
            sources.append({
                "brief_id": r.brief_id,
                "topic": r.topic,
                "swarm": r.swarm,
                "domain": r.domain,
                "similarity": round(r.similarity, 3),
            })

    context = "\n\n---\n\n".join(context_parts)

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model=config.LLM_MODEL,
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Контекст из исследовательских брифов:\n\n{context}\n\n---\n\nВопрос: {query}",
            }
        ],
    )

    answer = resp.content[0].text if resp.content else "Ошибка генерации ответа."
    logger.info(f"Synthesized answer for '{query[:60]}...' using {len(results)} chunks")

    return {"answer": answer, "sources": sources}
