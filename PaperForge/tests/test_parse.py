"""Tests for PaperForge parse module."""

import tempfile
from pathlib import Path

from paperforge.models.paper import generate_slug, normalize_title, Paper
from paperforge.parse.metadata import extract_doi, detect_language


class TestSlugGeneration:
    def test_basic_slug(self):
        assert generate_slug("Attention Is All You Need") == "attention-is-all-you-need"

    def test_special_chars(self):
        slug = generate_slug("BERT: Pre-training of Deep Bidirectional Transformers")
        assert ":" not in slug
        assert slug == "bert-pre-training-of-deep-bidirectional-transformers"

    def test_unicode(self):
        slug = generate_slug("基于Transformer的模型")
        # Should not crash, should produce something
        assert len(slug) > 0

    def test_max_length(self):
        long_title = "A " + "Very " * 50 + "Long Title"
        slug = generate_slug(long_title)
        assert len(slug) <= 60

    def test_empty(self):
        slug = generate_slug("")
        assert slug == ""


class TestNormalizeTitle:
    def test_basic(self):
        assert normalize_title("Attention Is All You Need") == "attention is all you need"

    def test_punctuation(self):
        norm = normalize_title("BERT: Pre-training of Deep Bidirectional Transformers!")
        assert ":" not in norm
        assert "!" not in norm
        assert "bert pretraining of deep bidirectional transformers" == norm

    def test_whitespace(self):
        norm = normalize_title("  Too   Many   Spaces  ")
        assert norm == "too many spaces"


class TestExtractDOI:
    def test_basic_doi(self):
        text = "DOI: 10.1234/abcd-5678"
        doi = extract_doi(text)
        assert doi == "10.1234/abcd-5678"

    def test_doi_in_url(self):
        text = "https://doi.org/10.1145/1234567.1234568"
        doi = extract_doi(text)
        assert doi is not None
        assert doi.startswith("10.")

    def test_no_doi(self):
        text = "This paper has no DOI."
        doi = extract_doi(text)
        assert doi is None


class TestDetectLanguage:
    def test_english(self):
        lang = detect_language("This is a research paper about natural language processing and machine learning.")
        assert lang == "en"

    def test_chinese(self):
        lang = detect_language("这是一篇关于自然语言处理和机器学习的研究论文，主要讨论了深度学习的应用场景。")
        assert lang == "zh"

    def test_empty(self):
        lang = detect_language("")
        assert lang == "unknown"

    def test_short(self):
        lang = detect_language("hi")
        assert lang == "unknown"


class TestPaperModel:
    def test_create_paper(self):
        p = Paper(title="Test Paper Title")
        assert p.slug == "test-paper-title"
        assert p.normalized_title == "test paper title"
        assert len(p.id) > 0
        assert p.status == "completed"

    def test_to_db_dict(self):
        p = Paper(title="Test", authors=["Alice", "Bob"])
        d = p.to_db_dict()
        assert d["title"] == "Test"
        assert isinstance(d["authors"], str)  # Should be string for DB

    def test_custom_id(self):
        p = Paper(id="custom-id-123", title="Test")
        assert p.id == "custom-id-123"
