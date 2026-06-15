"""Tests for the link module — citation graph and matching."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from paperforge.link.references import (
    find_references_section,
    extract_raw_references,
)
from paperforge.link.matcher import (
    normalize_title,
    match_by_doi,
    match_by_title,
    match_reference,
    MatchResult,
)
from paperforge.link.linker import generate_citation_section
from paperforge.store import db


# --- Fixtures ---


@pytest.fixture
def conn(tmp_path):
    """Create an in-memory SQLite database with schema."""
    db_path = tmp_path / "test.db"
    conn = db.init_db(db_path)
    yield conn
    conn.close()


@pytest.fixture
def sample_paper(conn):
    """Insert a sample paper."""
    paper = {
        "id": "paper-001",
        "slug": "attention-is-all-you-need",
        "title": "Attention is All You Need",
        "normalized_title": "attention is all you need",
        "authors": json.dumps(["Vaswani", "Shazeer", "Parmar"]),
        "year": 2017,
        "venue": "NeurIPS",
        "doi": "10.48550/arXiv.1706.03762",
    }
    db.insert_paper(conn, paper)
    return paper


@pytest.fixture
def sample_paper2(conn):
    """Insert a second sample paper."""
    paper = {
        "id": "paper-002",
        "slug": "bert-pre-training-of-deep-bidirectional",
        "title": "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding",
        "normalized_title": "bert pretraining of deep bidirectional transformers for language understanding",
        "authors": json.dumps(["Devlin", "Chang", "Lee", "Toutanova"]),
        "year": 2019,
        "venue": "NAACL",
        "doi": "10.18653/v1/N19-1423",
    }
    db.insert_paper(conn, paper)
    return paper


# --- Test normalize_title ---


class TestNormalizeTitle:
    def test_basic(self):
        assert normalize_title("Hello World") == "hello world"

    def test_punctuation(self):
        assert normalize_title("BERT: Pre-training of Deep") == "bert pretraining of deep"

    def test_unicode(self):
        result = normalize_title("Résumé of a Study")
        assert "resume" in result

    def test_whitespace(self):
        assert normalize_title("  multiple   spaces  ") == "multiple spaces"

    def test_empty(self):
        assert normalize_title("") == ""

    def test_special_chars(self):
        assert normalize_title("A+B=C: A Study (2024)") == "abc a study 2024"


# --- Test find_references_section ---


class TestFindReferencesSection:
    def test_standard_references(self):
        text = """# Introduction

Some text here.

## Methods

More text.

## References

1. Author A. Title A. Journal A, 2020.
2. Author B. Title B. Journal B, 2021.
"""
        result = find_references_section(text)
        assert result is not None
        assert "Author A" in result
        assert "Author B" in result

    def test_bibliography_header(self):
        text = """Some content.

# Bibliography

- Author A, Title A.
- Author B, Title B.
"""
        result = find_references_section(text)
        assert result is not None
        assert "Author A" in result

    def test_no_references(self):
        text = """# Introduction

Just an introduction, no references section.
"""
        result = find_references_section(text)
        assert result is None

    def test_references_at_end(self):
        text = """# Paper

Content.

## Conclusion

Conclusion text.

## References

[1] Smith et al. A paper. 2020.
[2] Jones et al. Another paper. 2021.
"""
        result = find_references_section(text)
        assert result is not None
        assert "Smith" in result
        assert "Jones" in result


# --- Test extract_raw_references ---


class TestExtractRawReferences:
    def test_numbered_brackets(self):
        ref_text = """[1] Vaswani et al. Attention is All You Need. NeurIPS, 2017.
[2] Devlin et al. BERT. NAACL, 2019.
[3] Brown et al. GPT-3. NeurIPS, 2020."""
        refs = extract_raw_references(ref_text)
        assert len(refs) == 3
        assert "Vaswani" in refs[0]
        assert "Devlin" in refs[1]

    def test_numbered_dot(self):
        ref_text = """1. Author A. Title A. 2020.
2. Author B. Title B. 2021."""
        refs = extract_raw_references(ref_text)
        assert len(refs) == 2

    def test_multiline_refs(self):
        ref_text = """[1] Vaswani A, Shazeer N, Parmar N,
    et al. Attention is All You Need.
    NeurIPS, 2017.
[2] Devlin J, et al. BERT. NAACL, 2019."""
        refs = extract_raw_references(ref_text)
        assert len(refs) == 2

    def test_empty(self):
        refs = extract_raw_references("")
        assert refs == []

    def test_mixed_numbered_and_author_year(self):
        """Test that author-year refs are correctly split even when numbered refs exist."""
        ref_text = """[1] Vaswani A, Shazeer N, Parmar N, et al. Attention is All You Need. NeurIPS, 2017.
[2] Devlin J, Chang M, Lee K, et al. BERT. NAACL, 2019.
[3] Brown T, et al. Language Models are Few-Shot Learners. NeurIPS, 2020.
Radford A, et al. Language Models are Unsupervised Multitask Learners. 2019.
[5] Liu Y, et al. RoBERTa. 2019."""
        refs = extract_raw_references(ref_text)
        assert len(refs) == 5
        assert "Vaswani" in refs[0]
        assert "Devlin" in refs[1]
        assert "Brown" in refs[2]
        assert "Radford" in refs[3]
        assert "Liu" in refs[4]

    def test_unnumbered_author_year(self):
        """Test author-year references without numbering."""
        ref_text = """Vaswani A, Shazeer N, Parmar N, et al. Attention is All You Need. NeurIPS, 2017.
Devlin J, Chang M, Lee K, et al. BERT. NAACL, 2019.
Brown T, et al. Language Models are Few-Shot Learners. NeurIPS, 2020."""
        refs = extract_raw_references(ref_text)
        assert len(refs) == 3
        assert "Vaswani" in refs[0]
        assert "Devlin" in refs[1]
        assert "Brown" in refs[2]


# --- Test match_by_doi ---


class TestMatchByDoi:
    def test_exact_match(self, conn, sample_paper):
        result = match_by_doi("10.48550/arXiv.1706.03762", conn)
        assert result == "paper-001"

    def test_no_match(self, conn, sample_paper):
        result = match_by_doi("10.1234/nonexistent", conn)
        assert result is None

    def test_empty_doi(self, conn, sample_paper):
        result = match_by_doi("", conn)
        assert result is None

    def test_doi_with_prefix(self, conn, sample_paper):
        result = match_by_doi("https://doi.org/10.48550/arXiv.1706.03762", conn)
        assert result == "paper-001"


# --- Test match_by_title ---


class TestMatchByTitle:
    def test_exact_match(self, conn, sample_paper):
        result = match_by_title(
            "Attention is All You Need",
            year=2017,
            conn=conn,
        )
        assert result is not None
        assert result.paper_id == "paper-001"
        assert result.status == "confirmed"
        assert result.confidence >= 0.95

    def test_close_match(self, conn, sample_paper):
        result = match_by_title(
            "Attention Is All You Need",  # Different capitalization
            year=2017,
            conn=conn,
        )
        assert result is not None
        assert result.paper_id == "paper-001"

    def test_no_match(self, conn, sample_paper):
        result = match_by_title(
            "Completely Different Paper Title",
            year=2020,
            conn=conn,
        )
        assert result is None

    def test_year_mismatch_skips(self, conn, sample_paper):
        result = match_by_title(
            "Attention is All You Need",
            year=2025,  # Far from 2017
            conn=conn,
            require_year=True,
        )
        assert result is None

    def test_empty_title(self, conn, sample_paper):
        result = match_by_title("", year=2017, conn=conn)
        assert result is None


# --- Test match_reference ---


class TestMatchReference:
    def test_doi_match(self, conn, sample_paper):
        ref = {
            "title": "Some Title",
            "year": 2017,
            "doi": "10.48550/arXiv.1706.03762",
        }
        result = match_reference(ref, conn)
        assert result.status == "confirmed"
        assert result.match_method == "doi"
        assert result.confidence == 1.0

    def test_title_match(self, conn, sample_paper):
        ref = {
            "title": "Attention is All You Need",
            "year": 2017,
            "doi": None,
        }
        result = match_reference(ref, conn)
        assert result.status == "confirmed"
        assert result.match_method == "title_fuzzy"

    def test_no_match(self, conn, sample_paper):
        ref = {
            "title": "Nonexistent Paper About Widgets",
            "year": 2024,
            "doi": None,
        }
        result = match_reference(ref, conn)
        assert result.status == "unmatched"


# --- Test citation edges ---


class TestCitationEdges:
    def test_create_and_query(self, conn, sample_paper, sample_paper2):
        # paper-001 cites paper-002
        db.insert_citation_edge(
            conn, "paper-001", "paper-002",
            match_method="doi", confidence=1.0,
        )

        # Check citing
        citing = db.get_citing_papers(conn, "paper-001")
        assert len(citing) == 1
        assert citing[0]["target_paper_id"] == "paper-002"

        # Check cited_by
        cited_by = db.get_cited_by_papers(conn, "paper-002")
        assert len(cited_by) == 1
        assert cited_by[0]["source_paper_id"] == "paper-001"

    def test_generate_citation_section(self, conn, sample_paper, sample_paper2):
        db.insert_citation_edge(
            conn, "paper-001", "paper-002",
            match_method="doi", confidence=1.0,
        )

        section = generate_citation_section("paper-001", conn)
        assert len(section["citing_papers"]) == 1
        assert section["citing_papers"][0]["slug"] == "bert-pre-training-of-deep-bidirectional"
        assert len(section["cited_by_papers"]) == 0

        section2 = generate_citation_section("paper-002", conn)
        assert len(section2["citing_papers"]) == 0
        assert len(section2["cited_by_papers"]) == 1

    def test_delete_edge(self, conn, sample_paper, sample_paper2):
        db.insert_citation_edge(
            conn, "paper-001", "paper-002",
            match_method="doi", confidence=1.0,
        )
        db.delete_citation_edge(conn, "paper-001", "paper-002")

        citing = db.get_citing_papers(conn, "paper-001")
        assert len(citing) == 0

    def test_pending_refs(self, conn, sample_paper):
        # Insert a pending candidate
        ref_id = "ref-001"
        now = "2026-01-01T00:00:00"
        conn.execute(
            """INSERT INTO references_raw
               (id, source_paper_id, raw_text, sequence_num, extraction_method, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (ref_id, "paper-001", "Some reference text", 1, "test", now),
        )
        conn.execute(
            """INSERT INTO reference_candidates
               (id, source_paper_id, raw_reference_id, title, confidence, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("cand-001", "paper-001", ref_id, "Pending Paper", 0.88, "pending", now, now),
        )
        conn.commit()

        section = generate_citation_section("paper-001", conn)
        assert len(section["pending_refs"]) == 1
        assert section["pending_refs"][0]["title"] == "Pending Paper"
