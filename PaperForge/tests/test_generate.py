"""Tests for PaperForge LLM generation module."""

import json
from pathlib import Path

from paperforge.llm.schemas import (
    SummaryResult, QAPair, QAResult, GlossaryEntry, GlossaryResult,
)
from paperforge.llm.prompts import (
    SUMMARY_SYSTEM, SUMMARY_USER, QA_SYSTEM, QA_USER,
    GLOSSARY_SYSTEM, GLOSSARY_USER, TRANSLATE_SYSTEM, TRANSLATE_USER,
)
from paperforge.generate.translator import _split_into_chunks


# --- Pydantic Model Tests ---

class TestSummaryResult:
    def test_create_default(self):
        result = SummaryResult()
        assert result.one_sentence_summary == ""
        assert result.research_question == ""
        assert result.method == ""

    def test_create_with_data(self):
        data = {
            "one_sentence_summary": "This paper proposes a new attention mechanism.",
            "research_question": "How to improve transformer efficiency?",
            "method": "Sparse attention with linear complexity.",
            "conclusions": "Achieves 2x speedup with comparable accuracy.",
            "use_cases": "Long document processing, real-time inference.",
            "limitations": "Not tested on multimodal tasks.",
            "relation_to_prior_work": "Extends Linformer with dynamic sparsity.",
        }
        result = SummaryResult(**data)
        assert result.one_sentence_summary == "This paper proposes a new attention mechanism."
        assert result.method == "Sparse attention with linear complexity."

    def test_from_json(self):
        json_str = '{"one_sentence_summary": "Test", "research_question": "Q", "method": "M", "conclusions": "C", "use_cases": "U", "limitations": "L", "relation_to_prior_work": "R"}'
        data = json.loads(json_str)
        result = SummaryResult(**data)
        assert result.one_sentence_summary == "Test"

    def test_partial_data(self):
        result = SummaryResult(one_sentence_summary="Only summary")
        assert result.one_sentence_summary == "Only summary"
        assert result.research_question == ""


class TestQAResult:
    def test_create_default(self):
        result = QAResult()
        assert result.questions == []

    def test_create_with_data(self):
        data = {
            "questions": [
                {"question": "What is the main contribution?", "answer": "A new architecture."},
                {"question": "What dataset was used?", "answer": "ImageNet."},
            ]
        }
        result = QAResult(**data)
        assert len(result.questions) == 2
        assert result.questions[0].question == "What is the main contribution?"
        assert result.questions[1].answer == "ImageNet."

    def test_qa_pair_model(self):
        pair = QAPair(question="Why?", answer="Because.")
        assert pair.question == "Why?"
        assert pair.answer == "Because."


class TestGlossaryResult:
    def test_create_default(self):
        result = GlossaryResult()
        assert result.entries == []

    def test_create_with_data(self):
        data = {
            "entries": [
                {"term_en": "Transformer", "term_zh": "变换器", "definition": "A neural network architecture.", "section": "Introduction"},
                {"term_en": "Attention", "term_zh": "注意力", "definition": "A mechanism for focusing on relevant parts.", "section": "Method"},
            ]
        }
        result = GlossaryResult(**data)
        assert len(result.entries) == 2
        assert result.entries[0].term_en == "Transformer"
        assert result.entries[0].term_zh == "变换器"
        assert result.entries[1].section == "Method"

    def test_glossary_entry_model(self):
        entry = GlossaryEntry(term_en="BERT", term_zh="BERT模型", definition="Bidirectional encoder", section="Background")
        assert entry.term_en == "BERT"


# --- Prompt Template Tests ---

class TestPrompts:
    def test_summary_user_has_placeholder(self):
        assert "{paper_text}" in SUMMARY_USER

    def test_qa_user_has_placeholder(self):
        assert "{paper_text}" in QA_USER

    def test_glossary_user_has_placeholder(self):
        assert "{paper_text}" in GLOSSARY_USER

    def test_translate_user_has_placeholder(self):
        assert "{text}" in TRANSLATE_USER

    def test_summary_system_mentions_json(self):
        assert "JSON" in SUMMARY_SYSTEM

    def test_qa_system_mentions_json(self):
        assert "JSON" in QA_SYSTEM

    def test_glossary_system_mentions_json(self):
        assert "JSON" in GLOSSARY_SYSTEM

    def test_summary_user_format(self):
        formatted = SUMMARY_USER.format(paper_text="test paper content")
        assert "test paper content" in formatted
        assert "one_sentence_summary" in formatted

    def test_qa_user_format(self):
        formatted = QA_USER.format(paper_text="test content")
        assert "test content" in formatted
        assert "questions" in formatted


# --- Chunk Splitting Tests ---

class TestChunkSplitting:
    def test_short_text_no_split(self):
        text = "Short text."
        chunks = _split_into_chunks(text, chunk_size=100)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_split_at_paragraph_boundary(self):
        text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
        chunks = _split_into_chunks(text, chunk_size=30)
        assert len(chunks) >= 2
        # Each chunk should be non-empty
        for chunk in chunks:
            assert len(chunk.strip()) > 0

    def test_empty_text(self):
        chunks = _split_into_chunks("", chunk_size=100)
        assert len(chunks) == 1

    def test_exact_boundary(self):
        text = "a" * 100
        chunks = _split_into_chunks(text, chunk_size=100)
        assert len(chunks) == 1

    def test_long_text_splits(self):
        paragraphs = ["Paragraph " + str(i) + ". " * 20 for i in range(20)]
        text = "\n\n".join(paragraphs)
        chunks = _split_into_chunks(text, chunk_size=200)
        assert len(chunks) > 1
        # Reconstruct should give back roughly the same content
        reconstructed = "\n\n".join(chunks)
        for i in range(20):
            assert f"Paragraph {i}" in reconstructed

    def test_single_long_paragraph(self):
        text = "x" * 500
        chunks = _split_into_chunks(text, chunk_size=100)
        assert len(chunks) >= 1
