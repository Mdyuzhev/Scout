"""Diser RAG — synthesizer: search + context assembly.

SC-042 fix: no server-side LLM calls.
/ask returns context chunks for the agent to synthesize.
Agent generates the answer using its own LLM (subscription), same as Scout SC-036.
"""

from loguru import logger

from . import config
from .searcher import Searcher

SYSTEM_PROMPT = """Ты — аналитик диссертационного исследования. Отвечай строго на основе
предоставленного контекста из исследовательских брифов. Язык ответа: русский.
Стиль: академическая проза, пригодная для включения в диссертацию.
Каждое утверждение подкреплять ссылкой в формате [SW2-004].
Если в контексте нет ответа — честно сообщи об этом.
Не добавляй информацию из общих знаний."""


def get_context(
    query: str,
    searcher: Searcher,
    domain: str | None = None,
    swarm: str | None = None,
) -> dict:
    """Search and return context for agent-side synthesis.

    Returns:
        context:        assembled text ready to pass to LLM
        sources:        list of source metadata
        chunks_count:   number of chunks found
        system_prompt:  prompt to use when generating the answer
        found:          True if any results found
    """
    results = searcher.search(query, domain=domain, swarm=swarm)

    if not results:
        logger.info(f"No results for query: '{query[:60]}'")
        return {
            "found": False,
            "context": "",
            "sources": [],
            "chunks_count": 0,
            "system_prompt": SYSTEM_PROMPT,
            "message": "В проиндексированных материалах не найдено релевантных данных.",
        }

    context_parts = []
    sources = []
    seen_briefs: set[str] = set()

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

    logger.info(
        f"Context assembled for '{query[:60]}': "
        f"{len(results)} chunks, {len(sources)} unique briefs"
    )

    return {
        "found": True,
        "context": context,
        "sources": sources,
        "chunks_count": len(results),
        "system_prompt": SYSTEM_PROMPT,
        "user_prompt": (
            f"Контекст из исследовательских брифов:\n\n{context}\n\n---\n\nВопрос: {query}"
        ),
    }
