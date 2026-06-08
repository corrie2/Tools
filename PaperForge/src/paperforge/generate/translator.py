"""Paper translation using LLM."""

from __future__ import annotations

import logging
from typing import List

from paperforge.llm.client import LLMClient
from paperforge.llm.prompts import TRANSLATE_SYSTEM, TRANSLATE_USER

logger = logging.getLogger(__name__)

DEFAULT_CHUNK_SIZE = 3000


def _split_into_chunks(text: str, chunk_size: int = DEFAULT_CHUNK_SIZE) -> List[str]:
    """Split text into chunks at paragraph boundaries.

    Args:
        text: Text to split.
        chunk_size: Target chunk size in characters.

    Returns:
        List of text chunks.
    """
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    paragraphs = text.split("\n\n")
    current = ""

    for para in paragraphs:
        if len(current) + len(para) + 2 > chunk_size and current:
            chunks.append(current.strip())
            current = para
        else:
            current = current + "\n\n" + para if current else para

    if current.strip():
        chunks.append(current.strip())

    return chunks if chunks else [text]


def translate_paper(
    paper_text: str,
    llm_client: LLMClient,
    mode: str = "abstract",
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> str:
    """Translate paper text to Chinese.

    Args:
        paper_text: Full paper markdown text.
        llm_client: LLM API client.
        mode: 'abstract' for abstract+conclusions only, 'full' for entire paper.
        chunk_size: Max characters per translation chunk.

    Returns:
        Translated text in Chinese.

    Raises:
        RuntimeError: If LLM call fails.
    """
    if mode == "abstract":
        # Extract abstract and conclusions sections
        text = _extract_abstract_and_conclusions(paper_text)
        if not text:
            logger.warning("Could not extract abstract/conclusions, translating first 3000 chars")
            text = paper_text[:3000]
    else:
        text = paper_text

    chunks = _split_into_chunks(text, chunk_size)
    logger.info("Translating %d chunks (mode=%s)", len(chunks), mode)

    translated_parts = []
    for i, chunk in enumerate(chunks):
        logger.info("Translating chunk %d/%d (%d chars)", i + 1, len(chunks), len(chunk))
        messages = [
            {"role": "system", "content": TRANSLATE_SYSTEM},
            {"role": "user", "content": TRANSLATE_USER.format(text=chunk)},
        ]

        response = llm_client.chat_completion(
            messages=messages,
            temperature=0.3,
            max_tokens=4096,
        )

        content = response["choices"][0]["message"]["content"]
        translated_parts.append(content)

    return "\n\n".join(translated_parts)


def _extract_abstract_and_conclusions(text: str) -> str:
    """Extract abstract and conclusions sections from paper text.

    Simple heuristic: look for 'abstract' and 'conclusion' headers.
    """
    import re

    sections = []
    text_lower = text.lower()

    # Find abstract
    abstract_match = re.search(
        r"(?:^|\n)#+\s*abstract\b.*?\n(.*?)(?=\n#+\s|\Z)",
        text, re.IGNORECASE | re.DOTALL,
    )
    if abstract_match:
        sections.append("## Abstract\n" + abstract_match.group(1).strip())
    else:
        # Try without markdown headers
        abstract_match = re.search(
            r"(?:^|\n)abstract[:\s]*\n(.*?)(?=\n(?:introduction|keywords|1\.|I\.)|\Z)",
            text, re.IGNORECASE | re.DOTALL,
        )
        if abstract_match:
            sections.append("## Abstract\n" + abstract_match.group(1).strip())

    # Find conclusion(s)
    conclusion_match = re.search(
        r"(?:^|\n)#+\s*conclusions?\b.*?\n(.*?)(?=\n#+\s|\Z)",
        text, re.IGNORECASE | re.DOTALL,
    )
    if conclusion_match:
        sections.append("## Conclusions\n" + conclusion_match.group(1).strip())

    return "\n\n".join(sections)
