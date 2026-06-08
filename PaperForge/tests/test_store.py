"""Tests for PaperForge store module — db CRUD and writer."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from paperforge.store import db
from paperforge.store.writer import (
    write_paper_md, write_index_md, write_papers_index,
    write_summary_md, write_qa_md, write_glossary_md, write_translate_md,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def conn(tmp_path):
    """Create a temporary SQLite database with schema."""
    db_path = tmp_path / "test.db"
    conn = db.init_db(db_path)
    yield conn
    conn.close()


@pytest.fixture
def sample_paper_dict():
    """A sample paper dict for insertion."""
    return {
        "id": "paper-001",
        "slug": "attention-is-all-you-need",
        "title": "Attention is All You Need",
        "normalized_title": "attention is all you need",
        "authors": json.dumps(["Vaswani", "Shazeer", "Parmar"]),
        "year": 2017,
        "venue": "NeurIPS",
        "doi": "10.48550/arXiv.1706.03762",
        "language": "en",
        "parser": "docling",
        "parse_quality": "high",
        "fallback_used": 0,
        "status": "completed",
    }


@pytest.fixture
def sample_paper2_dict():
    """A second sample paper dict."""
    return {
        "id": "paper-002",
        "slug": "bert-pre-training",
        "title": "BERT: Pre-training of Deep Bidirectional Transformers",
        "normalized_title": "bert pretraining of deep bidirectional transformers",
        "authors": json.dumps(["Devlin", "Chang"]),
        "year": 2019,
        "venue": "NAACL",
        "doi": "10.18653/v1/N19-1423",
        "language": "en",
        "parser": "docling",
        "parse_quality": "high",
        "fallback_used": 0,
        "status": "completed",
    }


# ============================================================
# Test Paper CRUD
# ============================================================


class TestPaperCRUD:
    def test_insert_and_get_by_id(self, conn, sample_paper_dict):
        db.insert_paper(conn, sample_paper_dict)
        result = db.get_paper_by_id(conn, "paper-001")
        assert result is not None
        assert result["title"] == "Attention is All You Need"
        assert result["year"] == 2017

    def test_insert_and_get_by_slug(self, conn, sample_paper_dict):
        db.insert_paper(conn, sample_paper_dict)
        result = db.get_paper_by_slug(conn, "attention-is-all-you-need")
        assert result is not None
        assert result["id"] == "paper-001"

    def test_insert_and_get_by_doi(self, conn, sample_paper_dict):
        db.insert_paper(conn, sample_paper_dict)
        result = db.get_paper_by_doi(conn, "10.48550/arXiv.1706.03762")
        assert result is not None
        assert result["id"] == "paper-001"

    def test_insert_and_get_by_sha256(self, conn, sample_paper_dict):
        sample_paper_dict["pdf_sha256"] = "abc123def456"
        db.insert_paper(conn, sample_paper_dict)
        result = db.get_paper_by_sha256(conn, "abc123def456")
        assert result is not None
        assert result["id"] == "paper-001"

    def test_get_nonexistent(self, conn):
        assert db.get_paper_by_id(conn, "nonexistent") is None
        assert db.get_paper_by_slug(conn, "nonexistent") is None
        assert db.get_paper_by_doi(conn, "nonexistent") is None

    def test_list_papers_empty(self, conn):
        assert db.list_papers(conn) == []

    def test_list_papers_multiple(self, conn, sample_paper_dict, sample_paper2_dict):
        db.insert_paper(conn, sample_paper_dict)
        db.insert_paper(conn, sample_paper2_dict)
        papers = db.list_papers(conn)
        assert len(papers) == 2

    def test_list_papers_order(self, conn, sample_paper_dict, sample_paper2_dict):
        db.insert_paper(conn, sample_paper_dict)
        db.insert_paper(conn, sample_paper2_dict)
        papers = db.list_papers(conn)
        # Should be ordered by year DESC, so 2019 first
        assert papers[0]["year"] == 2019
        assert papers[1]["year"] == 2017

    def test_update_paper_status(self, conn, sample_paper_dict):
        db.insert_paper(conn, sample_paper_dict)
        db.update_paper_status(conn, "paper-001", "partial")
        result = db.get_paper_by_id(conn, "paper-001")
        assert result["status"] == "partial"

    def test_insert_replace(self, conn, sample_paper_dict):
        """INSERT OR REPLACE should update existing record."""
        db.insert_paper(conn, sample_paper_dict)
        sample_paper_dict["title"] = "Updated Title"
        db.insert_paper(conn, sample_paper_dict)
        result = db.get_paper_by_id(conn, "paper-001")
        assert result["title"] == "Updated Title"

    def test_authors_json_roundtrip(self, conn, sample_paper_dict):
        db.insert_paper(conn, sample_paper_dict)
        result = db.get_paper_by_id(conn, "paper-001")
        assert isinstance(result["authors"], list)
        assert "Vaswani" in result["authors"]

    def test_authors_as_string(self, conn, sample_paper_dict):
        """Authors already as string should still work."""
        sample_paper_dict["authors"] = '["Alice"]'
        db.insert_paper(conn, sample_paper_dict)
        result = db.get_paper_by_id(conn, "paper-001")
        assert isinstance(result["authors"], list)
        assert result["authors"] == ["Alice"]


# ============================================================
# Test Paper Tasks
# ============================================================


class TestPaperTasks:
    def test_insert_and_get(self, conn, sample_paper_dict):
        db.insert_paper(conn, sample_paper_dict)
        task_id = db.insert_task(conn, "paper-001", "summary")
        assert len(task_id) > 0

        tasks = db.get_tasks_for_paper(conn, "paper-001")
        assert len(tasks) == 1
        assert tasks[0]["task_type"] == "summary"
        assert tasks[0]["status"] == "pending"

    def test_update_to_running(self, conn, sample_paper_dict):
        db.insert_paper(conn, sample_paper_dict)
        task_id = db.insert_task(conn, "paper-001", "summary")
        db.update_task_status(conn, task_id, "running")
        tasks = db.get_tasks_for_paper(conn, "paper-001")
        assert tasks[0]["status"] == "running"
        assert tasks[0]["started_at"] is not None

    def test_update_to_completed(self, conn, sample_paper_dict):
        db.insert_paper(conn, sample_paper_dict)
        task_id = db.insert_task(conn, "paper-001", "summary")
        db.update_task_status(conn, task_id, "completed", output_path="papers/2017/att/summary.md")
        tasks = db.get_tasks_for_paper(conn, "paper-001")
        assert tasks[0]["status"] == "completed"
        assert tasks[0]["output_path"] == "papers/2017/att/summary.md"
        assert tasks[0]["finished_at"] is not None

    def test_update_to_failed(self, conn, sample_paper_dict):
        db.insert_paper(conn, sample_paper_dict)
        task_id = db.insert_task(conn, "paper-001", "qa")
        db.update_task_status(conn, task_id, "failed", error="LLM timeout")
        tasks = db.get_tasks_for_paper(conn, "paper-001")
        assert tasks[0]["status"] == "failed"
        assert tasks[0]["error"] == "LLM timeout"

    def test_multiple_tasks(self, conn, sample_paper_dict):
        db.insert_paper(conn, sample_paper_dict)
        for tt in ["summary", "qa", "glossary", "translate"]:
            db.insert_task(conn, "paper-001", tt)
        tasks = db.get_tasks_for_paper(conn, "paper-001")
        assert len(tasks) == 4
        types = {t["task_type"] for t in tasks}
        assert types == {"summary", "qa", "glossary", "translate"}

    def test_tasks_ordered_by_created_at(self, conn, sample_paper_dict):
        db.insert_paper(conn, sample_paper_dict)
        t1 = db.insert_task(conn, "paper-001", "summary")
        t2 = db.insert_task(conn, "paper-001", "qa")
        tasks = db.get_tasks_for_paper(conn, "paper-001")
        assert tasks[0]["task_type"] == "summary"
        assert tasks[1]["task_type"] == "qa"


# ============================================================
# Test References Raw
# ============================================================


class TestReferencesRaw:
    def test_insert_and_get(self, conn, sample_paper_dict):
        db.insert_paper(conn, sample_paper_dict)
        ref = {
            "id": "ref-001",
            "source_paper_id": "paper-001",
            "raw_text": "Vaswani et al. Attention is All You Need. 2017.",
            "sequence_num": 1,
            "extraction_method": "llm",
        }
        db.insert_reference_raw(conn, ref)
        refs = db.get_references_for_paper(conn, "paper-001")
        assert len(refs) == 1
        assert "Vaswani" in refs[0]["raw_text"]

    def test_insert_ignored_duplicate(self, conn, sample_paper_dict):
        """INSERT OR IGNORE should not fail on duplicate ID."""
        db.insert_paper(conn, sample_paper_dict)
        ref = {
            "id": "ref-001",
            "source_paper_id": "paper-001",
            "raw_text": "Some reference",
            "sequence_num": 1,
            "extraction_method": "test",
        }
        db.insert_reference_raw(conn, ref)
        db.insert_reference_raw(conn, ref)  # Should not raise
        refs = db.get_references_for_paper(conn, "paper-001")
        assert len(refs) == 1


# ============================================================
# Test Reference Candidates
# ============================================================


class TestReferenceCandidates:
    def _insert_raw_ref(self, conn, ref_id, paper_id):
        """Helper to insert a raw reference (required by FK constraint)."""
        db.insert_reference_raw(conn, {
            "id": ref_id,
            "source_paper_id": paper_id,
            "raw_text": f"Reference {ref_id}",
            "sequence_num": 1,
            "extraction_method": "test",
        })

    def test_insert_and_get(self, conn, sample_paper_dict):
        db.insert_paper(conn, sample_paper_dict)
        self._insert_raw_ref(conn, "ref-001", "paper-001")
        cand = {
            "id": "cand-001",
            "source_paper_id": "paper-001",
            "raw_reference_id": "ref-001",
            "title": "Some Candidate Paper",
            "status": "pending",
        }
        db.insert_reference_candidate(conn, cand)
        cands = db.get_candidates_for_paper(conn, "paper-001")
        assert len(cands) == 1
        assert cands[0]["title"] == "Some Candidate Paper"

    def test_update_status(self, conn, sample_paper_dict):
        db.insert_paper(conn, sample_paper_dict)
        self._insert_raw_ref(conn, "ref-001", "paper-001")
        cand = {
            "id": "cand-001",
            "source_paper_id": "paper-001",
            "raw_reference_id": "ref-001",
            "title": "Some Paper",
            "status": "pending",
        }
        db.insert_reference_candidate(conn, cand)
        db.update_candidate_status(conn, "cand-001", "confirmed")
        cands = db.get_candidates_for_paper(conn, "paper-001")
        assert cands[0]["status"] == "confirmed"

    def test_get_pending(self, conn, sample_paper_dict):
        db.insert_paper(conn, sample_paper_dict)
        for i in range(3):
            ref_id = f"ref-{i:03d}"
            self._insert_raw_ref(conn, ref_id, "paper-001")
            cand = {
                "id": f"cand-{i:03d}",
                "source_paper_id": "paper-001",
                "raw_reference_id": ref_id,
                "title": f"Paper {i}",
                "status": "pending" if i < 2 else "confirmed",
            }
            db.insert_reference_candidate(conn, cand)
        pending = db.get_pending_candidates(conn)
        assert len(pending) == 2


# ============================================================
# Test Citation Edges
# ============================================================


class TestCitationEdges:
    def test_insert_and_get_citing(self, conn, sample_paper_dict, sample_paper2_dict):
        db.insert_paper(conn, sample_paper_dict)
        db.insert_paper(conn, sample_paper2_dict)
        db.insert_citation_edge(conn, "paper-001", "paper-002", "doi", 1.0)

        citing = db.get_citing_papers(conn, "paper-001")
        assert len(citing) == 1
        assert citing[0]["target_paper_id"] == "paper-002"
        assert citing[0]["slug"] == "bert-pre-training"

    def test_insert_and_get_cited_by(self, conn, sample_paper_dict, sample_paper2_dict):
        db.insert_paper(conn, sample_paper_dict)
        db.insert_paper(conn, sample_paper2_dict)
        db.insert_citation_edge(conn, "paper-001", "paper-002", "doi", 1.0)

        cited_by = db.get_cited_by_papers(conn, "paper-002")
        assert len(cited_by) == 1
        assert cited_by[0]["source_paper_id"] == "paper-001"

    def test_get_citation_edge(self, conn, sample_paper_dict, sample_paper2_dict):
        db.insert_paper(conn, sample_paper_dict)
        db.insert_paper(conn, sample_paper2_dict)
        db.insert_citation_edge(conn, "paper-001", "paper-002", "title_fuzzy", 0.95)

        edge = db.get_citation_edge(conn, "paper-001", "paper-002")
        assert edge is not None
        assert edge["match_method"] == "title_fuzzy"
        assert edge["confidence"] == 0.95

    def test_update_confirmed(self, conn, sample_paper_dict, sample_paper2_dict):
        db.insert_paper(conn, sample_paper_dict)
        db.insert_paper(conn, sample_paper2_dict)
        db.insert_citation_edge(conn, "paper-001", "paper-002")
        db.update_citation_confirmed(conn, "paper-001", "paper-002", True)

        edge = db.get_citation_edge(conn, "paper-001", "paper-002")
        assert edge["confirmed"] == 1

    def test_delete_edge(self, conn, sample_paper_dict, sample_paper2_dict):
        db.insert_paper(conn, sample_paper_dict)
        db.insert_paper(conn, sample_paper2_dict)
        db.insert_citation_edge(conn, "paper-001", "paper-002")
        db.delete_citation_edge(conn, "paper-001", "paper-002")

        edge = db.get_citation_edge(conn, "paper-001", "paper-002")
        assert edge is None

    def test_no_citing_papers(self, conn, sample_paper_dict):
        db.insert_paper(conn, sample_paper_dict)
        assert db.get_citing_papers(conn, "paper-001") == []

    def test_no_cited_by(self, conn, sample_paper_dict):
        db.insert_paper(conn, sample_paper_dict)
        assert db.get_cited_by_papers(conn, "paper-001") == []


# ============================================================
# Test Delete Paper
# ============================================================


class TestDeletePaper:
    def test_delete_paper_removes_all(self, conn, sample_paper_dict, sample_paper2_dict):
        db.insert_paper(conn, sample_paper_dict)
        db.insert_paper(conn, sample_paper2_dict)

        # Add tasks
        t1 = db.insert_task(conn, "paper-001", "summary")
        db.update_task_status(conn, t1, "completed")

        # Add citation edge
        db.insert_citation_edge(conn, "paper-001", "paper-002", "doi", 1.0)

        # Add raw ref (required by FK on candidates)
        db.insert_reference_raw(conn, {
            "id": "ref-001", "source_paper_id": "paper-001",
            "raw_text": "Some ref", "sequence_num": 1, "extraction_method": "test",
        })

        # Add candidate
        db.insert_reference_candidate(conn, {
            "id": "cand-001", "source_paper_id": "paper-001",
            "raw_reference_id": "ref-001", "title": "X", "status": "pending",
        })

        # Delete paper-001
        db.delete_paper(conn, "paper-001")

        # Verify paper-001 is gone
        assert db.get_paper_by_id(conn, "paper-001") is None

        # Verify all related records are gone
        assert db.get_tasks_for_paper(conn, "paper-001") == []
        assert db.get_references_for_paper(conn, "paper-001") == []
        assert db.get_candidates_for_paper(conn, "paper-001") == []
        assert db.get_citing_papers(conn, "paper-001") == []

        # Verify paper-002 still exists
        assert db.get_paper_by_id(conn, "paper-002") is not None

    def test_delete_paper_removes_incoming_edges(self, conn, sample_paper_dict, sample_paper2_dict):
        """Deleting a paper should also remove edges where it was a target."""
        db.insert_paper(conn, sample_paper_dict)
        db.insert_paper(conn, sample_paper2_dict)
        db.insert_citation_edge(conn, "paper-001", "paper-002", "doi", 1.0)

        # Delete the TARGET (paper-002)
        db.delete_paper(conn, "paper-002")

        # paper-001 should have no citing edges (the edge to paper-002 is gone)
        assert db.get_citing_papers(conn, "paper-001") == []

    def test_delete_nonexistent(self, conn):
        """Deleting a nonexistent paper should not raise."""
        db.delete_paper(conn, "nonexistent")  # Should not raise


# ============================================================
# Test Writer
# ============================================================


class TestWriter:
    def test_write_paper_md(self, tmp_path):
        papers_dir = write_paper_md(tmp_path, 2017, "test-slug", "# Paper Content\n\nHello.")
        assert papers_dir.exists()
        assert (papers_dir / "paper.md").exists()
        content = (papers_dir / "paper.md").read_text()
        assert "# Paper Content" in content

    def test_write_paper_md_with_figures(self, tmp_path):
        fig_src = tmp_path / "fig1.png"
        fig_src.write_bytes(b"fake image")
        figures = {"fig1.png": fig_src}
        papers_dir = write_paper_md(tmp_path, 2017, "test-slug", "# Paper", figures)
        fig_dir = papers_dir / "figures"
        assert fig_dir.exists()
        assert (fig_dir / "fig1.png").exists()

    def test_write_index_md(self, tmp_path):
        paper = {
            "id": "p1", "title": "Test", "slug": "test-slug",
            "year": 2017, "venue": "NeurIPS", "doi": "10.1234/test",
            "language": "en", "parser": "docling", "parse_quality": "high",
        }
        path = write_index_md(tmp_path, 2017, "test-slug", paper)
        assert path.exists()
        content = path.read_text()
        assert "Test" in content
        assert "2017" in content

    def test_write_papers_index(self, tmp_path):
        papers = [
            {"id": "p1", "title": "Paper A", "slug": "paper-a", "year": 2020, "authors": ["Alice"]},
            {"id": "p2", "title": "Paper B", "slug": "paper-b", "year": 2019, "authors": ["Bob"]},
        ]
        path = write_papers_index(tmp_path, papers)
        assert path.exists()
        content = path.read_text()
        assert "Paper A" in content
        assert "Paper B" in content

    def test_write_papers_index_empty(self, tmp_path):
        path = write_papers_index(tmp_path, [])
        assert path.exists()

    def test_write_summary_md(self, tmp_path):
        from paperforge.llm.schemas import SummaryResult
        result = SummaryResult(
            one_sentence_summary="Test summary",
            research_question="How?",
            method="ML",
            conclusions="Done",
            use_cases="Many",
            limitations="None",
            relation_to_prior_work="Extends prior",
        )
        path = write_summary_md(tmp_path, 2017, "test-slug", "Test Title", result)
        assert path.exists()
        content = path.read_text()
        assert "Test summary" in content

    def test_write_qa_md(self, tmp_path):
        from paperforge.llm.schemas import QAResult, QAPair
        result = QAResult(questions=[
            QAPair(question="What?", answer="This."),
        ])
        path = write_qa_md(tmp_path, 2017, "test-slug", "Test Title", result)
        assert path.exists()
        content = path.read_text()
        assert "What?" in content

    def test_write_glossary_md(self, tmp_path):
        from paperforge.llm.schemas import GlossaryResult, GlossaryEntry
        result = GlossaryResult(entries=[
            GlossaryEntry(term_en="AI", term_zh="AI", definition="Artificial Intelligence", section="Intro"),
        ])
        path = write_glossary_md(tmp_path, 2017, "test-slug", "Test Title", result)
        assert path.exists()
        content = path.read_text()
        assert "Artificial Intelligence" in content

    def test_write_translate_md(self, tmp_path):
        path = write_translate_md(tmp_path, 2017, "test-slug", "# Translated\n\nContent")
        assert path.exists()
        content = path.read_text()
        assert "Translated" in content


# ============================================================
# Test Schema
# ============================================================


class TestSchema:
    def test_schema_creates_tables(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn = db.init_db(db_path)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()
        assert "papers" in tables
        assert "paper_tasks" in tables
        assert "references_raw" in tables
        assert "reference_candidates" in tables
        assert "citation_edges" in tables

    def test_schema_creates_indexes(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn = db.init_db(db_path)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = [row[0] for row in cursor.fetchall()]
        conn.close()
        assert "idx_papers_slug" in indexes
        assert "idx_tasks_paper" in indexes
        assert "idx_edges_source" in indexes

    def test_foreign_keys_enabled(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn = db.init_db(db_path)
        cursor = conn.execute("PRAGMA foreign_keys")
        val = cursor.fetchone()
        conn.close()
        assert val[0] == 1

    def test_wal_mode(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn = db.init_db(db_path)
        cursor = conn.execute("PRAGMA journal_mode")
        val = cursor.fetchone()
        conn.close()
        assert val[0] == "wal"
