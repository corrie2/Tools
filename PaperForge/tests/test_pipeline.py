"""Tests for PaperForge pipeline and CLI commands."""

from __future__ import annotations

import json
import os
import sqlite3
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from paperforge.store import db
from paperforge.store.writer import write_paper_md, write_index_md, write_papers_index


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def runner():
    """Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def vault(tmp_path):
    """Create a minimal vault structure with config and db."""
    vault = tmp_path / "vault"
    vault.mkdir()
    config_dir = vault / "paperforge"
    config_dir.mkdir()
    papers_dir = vault / "papers"
    papers_dir.mkdir()
    return vault


@pytest.fixture
def vault_with_db(vault):
    """Vault with an initialized database."""
    conn = db.init_db(vault / "paperforge" / "paperforge.db")
    conn.close()
    return vault


@pytest.fixture
def vault_with_paper(vault_with_db):
    """Vault with a paper in the database and on disk."""
    vault = vault_with_db
    conn = db.init_db(vault / "paperforge" / "paperforge.db")

    paper = {
        "id": "paper-001",
        "slug": "test-paper",
        "title": "A Test Paper",
        "normalized_title": "a test paper",
        "authors": json.dumps(["Author A"]),
        "year": 2024,
        "venue": "TestConf",
        "doi": None,
        "language": "en",
        "pdf_path": "/fake/path.pdf",
        "pdf_sha256": "abc123",
        "vault_path": "papers/2024/test-paper/index.md",
        "paper_dir": "papers/2024/test-paper",
        "parser": "docling",
        "parse_quality": "high",
        "fallback_used": 0,
        "status": "completed",
    }
    db.insert_paper(conn, paper)

    # Add tasks
    for tt in ["summary", "qa", "glossary", "translate", "references"]:
        tid = db.insert_task(conn, "paper-001", tt)
        db.update_task_status(conn, tid, "completed")

    # Create paper files on disk
    paper_dir = vault / "papers" / "2024" / "test-paper"
    paper_dir.mkdir(parents=True, exist_ok=True)
    (paper_dir / "paper.md").write_text("# A Test Paper\n\n## References\n\n1. Ref A.", encoding="utf-8")
    write_index_md(vault, 2024, "test-paper", paper)
    write_papers_index(vault, [paper])

    conn.close()
    return vault


@pytest.fixture
def vault_with_two_papers(vault_with_db):
    """Vault with two papers that have a citation edge."""
    vault = vault_with_db
    conn = db.init_db(vault / "paperforge" / "paperforge.db")

    paper1 = {
        "id": "paper-001",
        "slug": "paper-a",
        "title": "Paper A",
        "normalized_title": "paper a",
        "authors": json.dumps(["Alice"]),
        "year": 2024,
        "venue": "ConfA",
        "paper_dir": "papers/2024/paper-a",
        "vault_path": "papers/2024/paper-a/index.md",
        "parser": "docling",
        "status": "completed",
    }
    paper2 = {
        "id": "paper-002",
        "slug": "paper-b",
        "title": "Paper B",
        "normalized_title": "paper b",
        "authors": json.dumps(["Bob"]),
        "year": 2023,
        "venue": "ConfB",
        "paper_dir": "papers/2023/paper-b",
        "vault_path": "papers/2023/paper-b/index.md",
        "parser": "docling",
        "status": "completed",
    }
    db.insert_paper(conn, paper1)
    db.insert_paper(conn, paper2)

    # Add citation: A cites B
    db.insert_citation_edge(conn, "paper-001", "paper-002", "doi", 1.0)

    # Add pending candidate for paper A
    ref_id = "ref-001"
    now = "2024-01-01T00:00:00"
    conn.execute(
        """INSERT INTO references_raw
           (id, source_paper_id, raw_text, sequence_num, extraction_method, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (ref_id, "paper-001", "Some raw reference", 1, "test", now),
    )
    conn.execute(
        """INSERT INTO reference_candidates
           (id, source_paper_id, raw_reference_id, title, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("cand-001", "paper-001", ref_id, "Pending Paper", "pending", now, now),
    )
    conn.commit()

    # Create files for both papers
    for p in [paper1, paper2]:
        pdir = vault / p["paper_dir"]
        pdir.mkdir(parents=True, exist_ok=True)
        (pdir / "paper.md").write_text(f"# {p['title']}\n\nContent.", encoding="utf-8")
        write_index_md(vault, p.get("year", 2024), p["slug"], p)

    write_papers_index(vault, [paper1, paper2])

    conn.close()
    return vault


# ============================================================
# Test CLI: list
# ============================================================


class TestListCommand:
    def test_list_empty(self, runner, vault_with_db):
        from paperforge.cli import cli
        result = runner.invoke(cli, ["list", "--vault", str(vault_with_db)])
        assert result.exit_code == 0
        assert "No papers" in result.output

    def test_list_with_paper(self, runner, vault_with_paper):
        from paperforge.cli import cli
        result = runner.invoke(cli, ["list", "--vault", str(vault_with_paper)])
        assert result.exit_code == 0
        assert "test-paper" in result.output
        assert "A Test Paper" in result.output
        assert "Total: 1 papers" in result.output

    def test_list_year_filter(self, runner, vault_with_paper):
        from paperforge.cli import cli
        result = runner.invoke(cli, ["list", "--vault", str(vault_with_paper), "--year", "2024"])
        assert result.exit_code == 0
        assert "test-paper" in result.output

        result = runner.invoke(cli, ["list", "--vault", str(vault_with_paper), "--year", "1999"])
        assert result.exit_code == 0
        assert "No papers match" in result.output

    def test_list_status_filter(self, runner, vault_with_paper):
        from paperforge.cli import cli
        result = runner.invoke(cli, ["list", "--vault", str(vault_with_paper), "--status", "completed"])
        assert result.exit_code == 0
        assert "test-paper" in result.output

        result = runner.invoke(cli, ["list", "--vault", str(vault_with_paper), "--status", "failed"])
        assert result.exit_code == 0
        assert "No papers match" in result.output


# ============================================================
# Test CLI: info
# ============================================================


class TestInfoCommand:
    def test_info_basic(self, runner, vault_with_paper):
        from paperforge.cli import cli
        result = runner.invoke(cli, ["info", "test-paper", "--vault", str(vault_with_paper)])
        assert result.exit_code == 0
        assert "A Test Paper" in result.output
        assert "Task Statuses" in result.output
        assert "Citation Summary" in result.output
        assert "Files" in result.output

    def test_info_not_found(self, runner, vault_with_db):
        from paperforge.cli import cli
        result = runner.invoke(cli, ["info", "nonexistent", "--vault", str(vault_with_db)])
        assert result.exit_code == 0
        assert "not found" in result.output


# ============================================================
# Test CLI: doctor
# ============================================================


class TestDoctorCommand:
    def test_doctor_basic(self, runner, vault_with_db):
        from paperforge.cli import cli
        result = runner.invoke(cli, ["doctor", "--vault", str(vault_with_db)])
        assert result.exit_code == 0
        assert "PaperForge Doctor" in result.output
        assert "Vault directory" in result.output

    def test_doctor_no_vault(self, runner, tmp_path):
        from paperforge.cli import cli
        result = runner.invoke(cli, ["doctor", "--vault", str(tmp_path / "nonexistent")])
        assert result.exit_code == 0
        assert "MISSING" in result.output


# ============================================================
# Test CLI: remove
# ============================================================


class TestRemoveCommand:
    def test_remove_with_confirmation(self, runner, vault_with_paper):
        from paperforge.cli import cli
        # Confirm yes
        result = runner.invoke(cli, ["remove", "test-paper", "--vault", str(vault_with_paper), "-y"])
        assert result.exit_code == 0
        assert "Removed" in result.output

        # Paper should be gone from db
        conn = db.init_db(vault_with_paper / "paperforge" / "paperforge.db")
        assert db.get_paper_by_slug(conn, "test-paper") is None
        conn.close()

        # Paper dir should be gone
        paper_dir = vault_with_paper / "papers" / "2024" / "test-paper"
        assert not paper_dir.exists()

    def test_remove_not_found(self, runner, vault_with_db):
        from paperforge.cli import cli
        result = runner.invoke(cli, ["remove", "nonexistent", "--vault", str(vault_with_db)])
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_remove_cleans_citation_edges(self, runner, vault_with_two_papers):
        from paperforge.cli import cli
        vault = vault_with_two_papers

        # Remove paper-a (which cites paper-b)
        result = runner.invoke(cli, ["remove", "paper-a", "--vault", str(vault), "-y"])
        assert result.exit_code == 0

        conn = db.init_db(vault / "paperforge" / "paperforge.db")
        # paper-b should still exist
        assert db.get_paper_by_slug(conn, "paper-b") is not None
        # No edges should remain for paper-a
        assert db.get_citing_papers(conn, "paper-001") == []
        # paper-b should have no cited_by
        assert db.get_cited_by_papers(conn, "paper-002") == []
        conn.close()

    def test_remove_regenerates_papers_index(self, runner, vault_with_two_papers):
        from paperforge.cli import cli
        vault = vault_with_two_papers

        result = runner.invoke(cli, ["remove", "paper-a", "--vault", str(vault), "-y"])
        assert result.exit_code == 0

        index_path = vault / "papers" / "index.md"
        assert index_path.exists()
        content = index_path.read_text()
        assert "paper-a" not in content
        assert "paper-b" in content or "Paper B" in content


# ============================================================
# Test CLI: rebuild-index
# ============================================================


class TestRebuildIndexCommand:
    def test_rebuild_basic(self, runner, vault_with_paper):
        from paperforge.cli import cli
        result = runner.invoke(cli, ["rebuild-index", "--vault", str(vault_with_paper)])
        assert result.exit_code == 0
        assert "Rebuilt" in result.output

        # Check that files were regenerated
        index_path = vault_with_paper / "papers" / "index.md"
        assert index_path.exists()

    def test_rebuild_empty(self, runner, vault_with_db):
        from paperforge.cli import cli
        result = runner.invoke(cli, ["rebuild-index", "--vault", str(vault_with_db)])
        assert result.exit_code == 0
        assert "No papers" in result.output

    def test_rebuild_two_papers(self, runner, vault_with_two_papers):
        from paperforge.cli import cli
        result = runner.invoke(cli, ["rebuild-index", "--vault", str(vault_with_two_papers)])
        assert result.exit_code == 0
        assert "Rebuilt 2/2" in result.output


# ============================================================
# Test CLI: open
# ============================================================


class TestOpenCommand:
    def test_open_not_found(self, runner, vault_with_db):
        from paperforge.cli import cli
        result = runner.invoke(cli, ["open", "nonexistent", "--vault", str(vault_with_db)])
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_open_no_index(self, runner, vault_with_db):
        """Paper exists in DB but index.md doesn't exist on disk."""
        conn = db.init_db(vault_with_db / "paperforge" / "paperforge.db")
        db.insert_paper(conn, {
            "id": "p1", "slug": "test", "title": "T",
            "paper_dir": "papers/2024/test",
        })
        conn.close()
        from paperforge.cli import cli
        result = runner.invoke(cli, ["open", "test", "--vault", str(vault_with_db)])
        assert result.exit_code != 0


# ============================================================
# Test CLI: export
# ============================================================


class TestExportCommand:
    def test_export_creates_zip(self, runner, vault_with_paper):
        from paperforge.cli import cli
        result = runner.invoke(cli, ["export", "--vault", str(vault_with_paper)])
        assert result.exit_code == 0
        assert "Export complete" in result.output

        # Find the zip file
        zips = list(vault_with_paper.glob("paperforge-export-*.zip"))
        assert len(zips) == 1

        # Verify contents
        with zipfile.ZipFile(str(zips[0]), "r") as zf:
            names = zf.namelist()
            assert any("paper.md" in n for n in names)
            assert "paperforge.db" in names

    def test_export_custom_output(self, runner, vault_with_paper):
        from paperforge.cli import cli
        output = vault_with_paper / "my-export.zip"
        result = runner.invoke(cli, ["export", "--vault", str(vault_with_paper), "-o", str(output)])
        assert result.exit_code == 0
        assert output.exists()

    def test_export_empty_vault(self, runner, tmp_path):
        """Export should fail if no papers directory or database."""
        from paperforge.cli import cli
        empty_vault = tmp_path / "empty"
        empty_vault.mkdir()
        result = runner.invoke(cli, ["export", "--vault", str(empty_vault)])
        assert result.exit_code != 0


# ============================================================
# Test Duplicate Detection (pipeline level)
# ============================================================


class TestDuplicateDetection:
    def test_same_sha256_detected(self, conn=None):
        """Test that get_paper_by_sha256 detects duplicates."""
        # Use a real tmp_path-based db
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            c = db.init_db(db_path)
            paper = {
                "id": "p1",
                "slug": "test",
                "title": "Test",
                "pdf_sha256": "abc123",
                "status": "completed",
            }
            db.insert_paper(c, paper)

            # Check duplicate
            found = db.get_paper_by_sha256(c, "abc123")
            assert found is not None
            assert found["id"] == "p1"

            # Check non-duplicate
            not_found = db.get_paper_by_sha256(c, "xyz789")
            assert not_found is None

            c.close()


# ============================================================
# Test CLI: confirm-ref / reject-ref
# ============================================================


class TestConfirmRejectRef:
    def test_confirm_creates_edge(self, runner, vault_with_two_papers):
        from paperforge.cli import cli
        vault = vault_with_two_papers
        result = runner.invoke(cli, ["confirm-ref", "paper-a", "paper-b", "--vault", str(vault)])
        assert result.exit_code == 0
        # Should succeed (either confirmed existing pending or created new edge)

    def test_reject_removes_edge(self, runner, vault_with_two_papers):
        from paperforge.cli import cli
        vault = vault_with_two_papers
        result = runner.invoke(cli, ["reject-ref", "paper-a", "paper-b", "--vault", str(vault)])
        assert result.exit_code == 0
