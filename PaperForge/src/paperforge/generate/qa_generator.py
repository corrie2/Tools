"""Q&A generation using LLM."""

from __future__ import annotations

import json
import logging


from paperforge.llm.client import LLMClient
from paperforge.llm.prompts import QA_SYSTEM, QA_USER
from paperforge.llm.schemas import QAResult

logger = logging.getLogger(__name__)

MAX_CHARS = 8000


def generate_qa(paper_text: str, llm_client: LLMClient) -> QAResult:
    """Generate Q&A pairs from a paper.

    Args:
        paper_text: Full paper markdown text.
        llm_client: LLM API client.

    Returns:
        QAResult with list of question-answer pairs.

    Raises:
        RuntimeError: If LLM call fails.
    """
    text = paper_text[:MAX_CHARS] if len(paper_text) > MAX_CHARS else paper_text

    messages = [
        {"role": "system", "content": QA_SYSTEM},
        {"role": "user", "content": QA_USER.format(paper_text=text)},
    ]

    response = llm_client.chat_completion(
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0.4,
        max_tokens=4096,
    )

    content = response["choices"][0]["message"]["content"]
    data = json.loads(content)

    # Validate required fields
    if "questions" not in data:
        logger.warning("LLM response missing 'questions' field")
        data["questions"] = []

    result = QAResult(**data)
    logger.info("Generated %d Q&A pairs", len(result.questions))
    return result
