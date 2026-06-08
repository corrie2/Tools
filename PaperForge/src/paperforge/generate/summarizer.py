"""Summary generation using LLM."""

from __future__ import annotations

import json
import logging
from typing import Optional

from paperforge.llm.client import LLMClient
from paperforge.llm.prompts import SUMMARY_SYSTEM, SUMMARY_USER
from paperforge.llm.schemas import SummaryResult

logger = logging.getLogger(__name__)

MAX_CHARS = 8000


def generate_summary(paper_text: str, llm_client: LLMClient) -> SummaryResult:
    """Generate a structured summary of a paper.

    Args:
        paper_text: Full paper markdown text.
        llm_client: LLM API client.

    Returns:
        SummaryResult with structured summary fields.

    Raises:
        RuntimeError: If LLM call fails.
    """
    # Truncate if too long
    text = paper_text[:MAX_CHARS] if len(paper_text) > MAX_CHARS else paper_text

    messages = [
        {"role": "system", "content": SUMMARY_SYSTEM},
        {"role": "user", "content": SUMMARY_USER.format(paper_text=text)},
    ]

    response = llm_client.chat_completion(
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0.3,
        max_tokens=2048,
    )

    content = response["choices"][0]["message"]["content"]
    data = json.loads(content)

    result = SummaryResult(**data)
    logger.info("Generated summary: %s", result.one_sentence_summary[:80])
    return result
