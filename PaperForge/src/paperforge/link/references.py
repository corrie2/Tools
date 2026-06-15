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


def _is_numbered_ref_start(line: str) -> Optional[int]:
    """Check if a line starts a new numbered reference.

    Returns the reference number if matched, None otherwise.

    Handles: [1], [1] Author, 1. Author, 1 Author
    Rejects years (1900-2099) and page numbers as false positives.
    """
    patterns = [
        (r"^\[(\d+)\]", True),           # [1] or [1] Author
        (r"^(\d+)\.\s+[A-Z(]", False),   # 1. Author  (need uppercase or paren after dot)
        (r"^(\d+)\s+[A-Z][a-z]", False), # 1 Author   (need capitalized word)
    ]
    for pattern, bracket_form in patterns:
        m = re.match(pattern, line)
        if m:
            num = int(m.group(1))
            # Reject years and page numbers
            if 1900 <= num <= 2099:
                continue
            if num > 500:
                continue
            return num
    return None


def _is_author_year_start(line: str) -> bool:
    """Check if a line starts a new author-year reference (no numbering).

    Patterns: Author, A. / Author A, / Author et al. / Authors and ...
    """
    return bool(re.match(
        r"^[A-Z][a-z]+(?:\s+(?:et\s+al|[A-Z]\b|and\b|de\b|van\b|von\b|le\b|la\b))",
        line,
    ))


def extract_raw_references(ref_text: str) -> List[str]:
    """Split the references section text into individual reference strings.

    Supports:
    - Numbered references: [1], [2] or 1., 2. or 1 Author...
    - Author-year references: Author, A. Title. (no numbering)
    - Multi-line references (wrapped lines)
    - Rejects years/page numbers as false reference starts
    """
    lines = ref_text.strip().split("\n")
    refs: List[str] = []
    current: List[str] = []
    last_ref_num: int = 0  # Track expected next reference number
    has_numbering: Optional[bool] = None  # None = not yet determined

    for line in lines:
        stripped = line.strip()
        if not stripped:
            # Blank line: soft separator — only flush if it looks like a boundary
            if current:
                joined = " ".join(current)
                # Flush if the accumulated text ends like a complete reference
                if re.search(r"(?:19|20)\d{2}[a-z.)]?\s*$", joined) or \
                   joined.rstrip().endswith("."):
                    refs.append(joined)
                    current = []
            continue

        num = _is_numbered_ref_start(stripped)

        if has_numbering is None:
            # First line: determine format
            if num is not None:
                has_numbering = True
                last_ref_num = num
            else:
                has_numbering = False

        is_new_ref = False

        if has_numbering and num is not None:
            if current:
                refs.append(" ".join(current))
                current = []
                is_new_ref = True
            elif num == last_ref_num + 1 or (not refs and num == 1):
                is_new_ref = True
                last_ref_num = num
            elif num <= last_ref_num:
                # Number went backwards or repeated — likely continuation text
                is_new_ref = False
            else:
                is_new_ref = True
                last_ref_num = num

        elif not has_numbering:
            # Author-year format: detect new reference start
            if _is_author_year_start(stripped) and current:
                # Check that accumulated text looks complete
                joined = " ".join(current)
                if re.search(r"(?:19|20)\d{2}", joined) or joined.rstrip().endswith("."):
                    refs.append(joined)
                    current = []
                    is_new_ref = True

        if is_new_ref:
            current = [stripped]
        else:
            current.append(stripped)

    if current:
        refs.append(" ".join(current))

    # Clean up: remove leading numbers/brackets
    cleaned: List[str] = []
    for ref in refs:
        ref = ref.strip()
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
