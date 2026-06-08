"""Pydantic models for validating LLM output."""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class SummaryResult(BaseModel):
    """Structured summary of an academic paper."""

    one_sentence_summary: str = ""
    research_question: str = ""
    method: str = ""
    conclusions: str = ""
    use_cases: str = ""
    limitations: str = ""
    relation_to_prior_work: str = ""


class QAPair(BaseModel):
    """A single question-answer pair."""

    question: str = ""
    answer: str = ""


class QAResult(BaseModel):
    """Collection of Q&A pairs from a paper."""

    questions: List[QAPair] = Field(default_factory=list)


class GlossaryEntry(BaseModel):
    """A single glossary entry with bilingual terms."""

    term_en: str = ""
    term_zh: str = ""
    definition: str = ""
    section: str = ""


class GlossaryResult(BaseModel):
    """Collection of glossary entries from a paper."""

    entries: List[GlossaryEntry] = Field(default_factory=list)
