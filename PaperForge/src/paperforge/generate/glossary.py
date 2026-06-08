"""Glossary extraction using LLM."""

from __future__ import annotations

import json
import logging


from paperforge.llm.client import LLMClient
from paperforge.llm.prompts import GLOSSARY_SYSTEM, GLOSSARY_USER
from paperforge.llm.schemas import GlossaryResult

logger = logging.getLogger(__name__)

MAX_CHARS = 8000


def generate_glossary(paper_text: str, llm_client: LLMClient) -> GlossaryResult:
    """Extract technical terms and definitions from a paper.

    Args:
        paper_text: Full paper markdown text.
        llm_client: LLM API client.

    Returns:
        GlossaryResult with list of glossary entries.

    Raises:
        RuntimeError: If LLM call fails.
    """
    text = paper_text[:MAX_CHARS] if len(paper_text) > MAX_CHARS else paper_text

    messages = [
        {"role": "system", "content": GLOSSARY_SYSTEM},
        {"role": "user", "content": GLOSSARY_USER.format(paper_text=text)},
    ]

    response = llm_client.chat_completion(
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0.3,
        max_tokens=4096,
    )

    content = response["choices"][0]["message"]["content"]
    data = json.loads(content)

    # Validate required fields
    if "entries" not in data:
        logger.warning("LLM response missing 'entries' field")
        data["entries"] = []

    result = GlossaryResult(**data)
    logger.info("Generated %d glossary entries", len(result.entries))
    return result
