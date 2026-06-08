"""Tests for improved metadata extraction and Semantic Scholar integration."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from paperforge.parse.metadata import (
    extract_doi,
    detect_language,
    _strip_affiliation_numbers,
)
from paperforge.models.paper import generate_slug, normalize_title, Paper


# --- Test header noise filtering ---

class TestHeaderNoiseFilter:
    """Test that title extraction filters out arXiv headers, etc."""

    def test_strip_affiliation_numbers_basic(self):
        result = _strip_affiliation_numbers("Alice 1,2 Bob 3")
        assert "Alice" in result
        assert "Bob" in result
        assert "1" not in result
        assert "3" not in result

    def test_strip_affiliation_numbers_complex(self):
        result = _strip_affiliation_numbers("John Doe 1, Jane Smith 2,3")
        assert "John Doe" in result
        assert "Jane Smith" in result

    def test_strip_affiliation_numbers_no_numbers(self):
        assert _strip_affiliation_numbers("Alice, Bob") == "Alice, Bob"

    def test_strip_affiliation_numbers_leading_digits(self):
        result = _strip_affiliation_numbers("1 Department of CS, MIT")
        assert "Department" in result


# --- Test Semantic Scholar functions (mocked) ---

class TestSemanticScholarAPI:
    """Test Semantic Scholar integration with mocked HTTP responses."""

    @patch("paperforge.link.semantic_scholar._api_get")
    def test_search_by_title(self, mock_api):
        from paperforge.link.semantic_scholar import search_by_title

        mock_api.return_value = {
            "data": [
                {
                    "title": "Attention Is All You Need",
                    "authors": [
                        {"name": "Ashish Vaswani"},
                        {"name": "Noam Shazeer"},
                    ],
                    "year": 2017,
                    "venue": "NeurIPS",
                    "externalIds": {"DOI": "10.48550/arXiv.1706.03762"},
                    "paperId": "abc123",
                    "abstract": "We propose a new architecture.",
                }
            ]
        }
        result = search_by_title("Attention Is All You Need")
        assert result is not None
        assert result["title"] == "Attention Is All You Need"
        assert result["year"] == 2017
        assert result["venue"] == "NeurIPS"
        assert result["doi"] == "10.48550/arXiv.1706.03762"
        assert result["paperId"] == "abc123"
        assert len(result["authors"]) == 2
        assert result["abstract"] == "We propose a new architecture."

    @patch("paperforge.link.semantic_scholar._api_get")
    def test_search_by_title_not_found(self, mock_api):
        from paperforge.link.semantic_scholar import search_by_title

        mock_api.return_value = {"data": []}
        result = search_by_title("Nonexistent Paper")
        assert result is None

    @patch("paperforge.link.semantic_scholar._api_get")
    def test_get_paper_by_doi(self, mock_api):
        from paperforge.link.semantic_scholar import get_paper_by_doi

        mock_api.return_value = {
            "title": "BERT",
            "authors": [{"name": "Jacob Devlin"}],
            "year": 2019,
            "venue": "NAACL",
            "externalIds": {"DOI": "10.18653/v1/N19-1423"},
            "paperId": "xyz789",
        }
        result = get_paper_by_doi("10.18653/v1/N19-1423")
        assert result is not None
        assert result["title"] == "BERT"
        assert result["paperId"] == "xyz789"

    @patch("paperforge.link.semantic_scholar._api_get")
    def test_get_paper_by_doi_not_found(self, mock_api):
        from paperforge.link.semantic_scholar import get_paper_by_doi

        mock_api.return_value = None
        result = get_paper_by_doi("10.1234/nonexistent")
        assert result is None

    @patch("paperforge.link.semantic_scholar.get_paper_by_doi")
    @patch("paperforge.link.semantic_scholar.search_by_title")
    def test_enrich_metadata_doi_priority(self, mock_search, mock_doi):
        from paperforge.link.semantic_scholar import enrich_metadata

        mock_doi.return_value = {
            "title": "Found by DOI",
            "authors": ["Alice"],
            "year": 2020,
            "venue": "ICML",
            "doi": "10.1234/test",
            "paperId": "id1",
        }
        result = enrich_metadata(doi="10.1234/test", title="Some Title")
        assert result is not None
        assert result["title"] == "Found by DOI"
        mock_doi.assert_called_once_with("10.1234/test")
        mock_search.assert_not_called()

    @patch("paperforge.link.semantic_scholar.get_paper_by_doi")
    @patch("paperforge.link.semantic_scholar.search_by_title")
    def test_enrich_metadata_fallback_to_title(self, mock_search, mock_doi):
        from paperforge.link.semantic_scholar import enrich_metadata

        mock_doi.return_value = None
        mock_search.return_value = {
            "title": "Found by Title",
            "authors": ["Bob"],
            "year": 2021,
            "venue": "ACL",
            "doi": None,
            "paperId": "id2",
        }
        result = enrich_metadata(doi="10.1234/nonexistent", title="Found by Title Search")
        assert result is not None
        assert result["title"] == "Found by Title"

    @patch("paperforge.link.crossref.search_by_title")
    @patch("paperforge.link.crossref.get_paper_by_doi")
    @patch("paperforge.link.semantic_scholar.get_paper_by_doi")
    @patch("paperforge.link.semantic_scholar.search_by_title")
    def test_enrich_metadata_no_results(self, mock_s2_search, mock_s2_doi, mock_cf_doi, mock_cf_search):
        from paperforge.link.semantic_scholar import enrich_metadata

        mock_s2_doi.return_value = None
        mock_s2_search.return_value = None
        mock_cf_doi.return_value = None
        mock_cf_search.return_value = None
        result = enrich_metadata(doi="10.1234/nope", title="Nothing Found Here")
        assert result is None

    @patch("paperforge.link.semantic_scholar._api_get")
    def test_resolve_reference_doi(self, mock_api):
        from paperforge.link.semantic_scholar import resolve_reference_doi

        mock_api.return_value = {
            "data": [{
                "title": "Some Reference",
                "authors": [],
                "year": 2020,
                "venue": "",
                "externalIds": {"DOI": "10.5555/ref"},
                "paperId": "ref1",
            }]
        }
        doi = resolve_reference_doi("Some Reference Title That Is Long Enough")
        assert doi == "10.5555/ref"

    @patch("paperforge.link.semantic_scholar._api_get")
    def test_resolve_reference_doi_short_title(self, mock_api):
        from paperforge.link.semantic_scholar import resolve_reference_doi

        doi = resolve_reference_doi("Hi")
        assert doi is None
        mock_api.assert_not_called()


# --- Test Paper model with external_id ---

class TestPaperExternalId:
    def test_paper_with_external_id(self):
        p = Paper(title="Test", external_id="s2id123")
        assert p.external_id == "s2id123"
        d = p.to_db_dict()
        assert d["external_id"] == "s2id123"

    def test_paper_without_external_id(self):
        p = Paper(title="Test")
        assert p.external_id is None
        d = p.to_db_dict()
        assert d["external_id"] is None

    def test_paper_with_venue(self):
        p = Paper(title="Test", venue="NeurIPS")
        assert p.venue == "NeurIPS"


# --- Test config auto-creation ---

class TestConfigAutoCreation:
    def test_load_config_creates_directory(self, tmp_path):
        from paperforge.config import load_config
        vault = tmp_path / "vault"
        assert not vault.exists()
        config = load_config(vault)
        assert config.data_path.exists()

    def test_create_default_config(self, tmp_path):
        from paperforge.config import create_default_config
        vault = tmp_path / "vault"
        vault.mkdir()
        path = create_default_config(vault)
        assert path.exists()
        content = path.read_text()
        assert "PaperForge configuration" in content
        assert "deepseek" in content

    def test_create_default_config_does_not_overwrite(self, tmp_path):
        from paperforge.config import create_default_config
        vault = tmp_path / "vault"
        vault.mkdir()
        config_dir = vault / "paperforge"
        config_dir.mkdir()
        config_path = config_dir / "config.yaml"
        config_path.write_text("custom: true", encoding="utf-8")
        create_default_config(vault)
        assert config_path.read_text() == "custom: true"


# --- Test CLI list --format json ---

class TestListJsonFormat:
    def test_list_json_no_papers(self, runner=None):
        from click.testing import CliRunner
        from paperforge.cli import cli
        import tempfile

        r = CliRunner()
        with tempfile.TemporaryDirectory() as tmpdir:
            vault = Path(tmpdir) / "vault"
            vault.mkdir()
            (vault / "paperforge").mkdir()
            result = r.invoke(cli, ["list", "--vault", str(vault), "--format", "json"])
            assert result.exit_code == 0
            assert result.output.strip() == "[]"

    def test_list_json_with_paper(self):
        from click.testing import CliRunner
        from paperforge.cli import cli
        from paperforge.store import db
        import tempfile

        r = CliRunner()
        with tempfile.TemporaryDirectory() as tmpdir:
            vault = Path(tmpdir) / "vault"
            vault.mkdir()
            config_dir = vault / "paperforge"
            config_dir.mkdir()
            papers_dir = vault / "papers"
            papers_dir.mkdir()

            conn = db.init_db(vault / "paperforge" / "paperforge.db")
            db.insert_paper(conn, {
                "id": "p1", "slug": "test-paper", "title": "Test Paper",
                "normalized_title": "test paper", "year": 2024,
                "venue": "ICML", "status": "completed",
                "paper_dir": "papers/2024/test-paper",
            })
            conn.close()

            result = r.invoke(cli, ["list", "--vault", str(vault), "--format", "json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert len(data) == 1
            assert data[0]["slug"] == "test-paper"
            assert data[0]["title"] == "Test Paper"
            assert data[0]["year"] == 2024
            assert data[0]["venue"] == "ICML"

    def test_list_json_with_limit(self):
        from click.testing import CliRunner
        from paperforge.cli import cli
        from paperforge.store import db
        import tempfile

        r = CliRunner()
        with tempfile.TemporaryDirectory() as tmpdir:
            vault = Path(tmpdir) / "vault"
            vault.mkdir()
            (vault / "paperforge").mkdir()
            (vault / "papers").mkdir()

            conn = db.init_db(vault / "paperforge" / "paperforge.db")
            for i in range(5):
                db.insert_paper(conn, {
                    "id": f"p{i}", "slug": f"paper-{i}", "title": f"Paper {i}",
                    "normalized_title": f"paper {i}", "year": 2024 - i,
                    "status": "completed",
                })
            conn.close()

            result = r.invoke(cli, ["list", "--vault", str(vault), "--format", "json", "--limit", "2"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert len(data) == 2

    def test_list_sort_by_title(self):
        from click.testing import CliRunner
        from paperforge.cli import cli
        from paperforge.store import db
        import tempfile

        r = CliRunner()
        with tempfile.TemporaryDirectory() as tmpdir:
            vault = Path(tmpdir) / "vault"
            vault.mkdir()
            (vault / "paperforge").mkdir()
            (vault / "papers").mkdir()

            conn = db.init_db(vault / "paperforge" / "paperforge.db")
            for i, title in enumerate(["Zebra", "Apple", "Mango"]):
                db.insert_paper(conn, {
                    "id": f"p{i}", "slug": title.lower(), "title": title,
                    "normalized_title": title.lower(), "year": 2024,
                    "status": "completed",
                })
            conn.close()

            result = r.invoke(cli, ["list", "--vault", str(vault), "--format", "json", "--sort", "title"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data[0]["title"] == "Apple"
            assert data[1]["title"] == "Mango"
            assert data[2]["title"] == "Zebra"
