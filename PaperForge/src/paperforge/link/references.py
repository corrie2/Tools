"""Extract and structure references from paper.md text."""

from __future__ import annotations

import json
import logging
import re
from typing import List, Optional

logger = logging.getLogger(__name__)

# Section headers that indicate the references section
REF_HEADERS = [
    r"^#+\s*References?\s*$",
    r"^#+\s*Bibliography\s*$",
    r"^#+\s*参考文献\s*$",
    r"^References?\s*$",
    r"^Bibliography\s*$",
    r"^#+\s*Works\s+Cited\s*$",
    r"^#+\s*Literature\s+Cited\s*$",
]


def find_references_section(text: str) -> Optional[str]:
    """Locate the References/Bibliography section at the end of paper.md.

    Scans from the end of the text upwards for a heading matching known
    reference section headers.  Returns the text after that heading, or
    None if not found.
    """
    lines = text.split("\n")

    # Find the last matching header
    header_idx = None
    for i in range(len(lines) - 1, -1, -1):
        line = lines[i].strip()
        for pattern in REF_HEADERS:
            if re.match(pattern, line, re.IGNORECASE):
                header_idx = i
                break
        if header_idx is not None:
            break

    if header_idx is None:
        return None

    # Return everything after the header
    ref_lines = lines[header_idx + 1:]
    ref_text = "\n".join(ref_lines).strip()
    return ref_text if ref_text else None


def extract_raw_references(ref_text: str) -> List[str]:
    """Split the references section text into individual reference strings.

    Supports:
    - Numbered references: [1], [2] or 1., 2. or [1] Author...
    - Plain lines (one reference per line)
    - Consecutive lines that belong to the same reference (wrapped lines)
    """
    lines = ref_text.strip().split("\n")
    refs: List[str] = []
    current: List[str] = []

    # Patterns for a new reference entry
    number_patterns = [
        r"^\[(\d+)\]",          # [1] Author...
        r"^(\d+)\.\s",          # 1. Author...
        r"^\[(\d+)\]\s",        # [1] Author...
        r"^(\d+)\s+[A-Z]",      # 1 Author... (common in some formats)
    ]

    for line in lines:
        stripped = line.strip()
        if not stripped:
            # Blank line might separate references
            if current:
                refs.append(" ".join(current))
                current = []
            continue

        is_new_ref = False
        for pattern in number_patterns:
            if re.match(pattern, stripped):
                is_new_ref = True
                break

        if is_new_ref and current:
            refs.append(" ".join(current))
            current = [stripped]
        else:
            current.append(stripped)

    if current:
        refs.append(" ".join(current))

    # Clean up: remove leading numbers/brackets
    cleaned: List[str] = []
    for ref in refs:
        ref = ref.strip()
        # Remove leading [N] or N.
        ref = re.sub(r"^\[\d+\]\s*", "", ref)
        ref = re.sub(r"^\d+\.\s*", "", ref)
        if ref:
            cleaned.append(ref)

    return cleaned


STRUCTURE_PROMPT = """Extract structured metadata from these academic references.

For EACH reference, output a JSON object with these fields:
- "authors": list of author name strings
- "title": the paper/article title
- "year": publication year as integer (null if unknown)
- "venue": journal/conference name (null if unknown)
- "doi": DOI string (null if not present)

Output a JSON array of objects.  Return ONLY valid JSON, no explanation.

References:
{references}"""


def structure_references(
    raw_refs: List[str],
    llm_client,
    batch_size: int = 10,
) -> List[dict]:
    """Use LLM to parse raw reference strings into structured metadata.

    Args:
        raw_refs: List of raw reference strings.
        llm_client: LLMClient instance.
        batch_size: Max references per LLM call.

    Returns:
        List of dicts with keys: authors, title, year, venue, doi.
    """
    all_structured: List[dict] = []

    for i in range(0, len(raw_refs), batch_size):
        batch = raw_refs[i:i + batch_size]

        # Format references for the prompt
        numbered = []
        for idx, ref in enumerate(batch, 1):
            numbered.append(f"{idx}. {ref}")
        references_text = "\n".join(numbered)

        prompt = STRUCTURE_PROMPT.format(references=references_text)

        try:
            response = llm_client.chat_completion(
                messages=[
                    {"role": "system", "content": "You are a reference parsing assistant. Output only valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=4096,
                response_format={"type": "json_object"},
            )

            content = response["choices"][0]["message"]["content"]
            parsed = json.loads(content)

            # Handle both {"references": [...]} and [...] formats
            if isinstance(parsed, dict):
                items = parsed.get("references", parsed.get("data", []))
                if isinstance(items, list):
                    all_structured.extend(items)
                else:
                    logger.warning("Unexpected LLM response structure: %s", list(parsed.keys()))
            elif isinstance(parsed, list):
                all_structured.extend(parsed)
            else:
                logger.warning("Unexpected LLM response type: %s", type(parsed))

        except Exception as e:
            logger.warning("Failed to structure references batch %d-%d: %s", i, i + batch_size, e)
            # Add stubs for the failed batch
            for ref in batch:
                all_structured.append({
                    "authors": [],
                    "title": "",
                    "year": None,
                    "venue": None,
                    "doi": None,
                    "_raw": ref,
                    "_error": str(e),
                })

    # Attach raw text to each structured reference
    for idx, s in enumerate(all_structured):
        if idx < len(raw_refs):
            s.setdefault("_raw", raw_refs[idx])

    return all_structured
