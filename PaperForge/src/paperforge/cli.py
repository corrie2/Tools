"""PaperForge CLI — command-line interface."""

from __future__ import annotations

import io
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import click
import yaml

from paperforge.config import load_config
from paperforge.store import db
from paperforge.store.writer import (
    write_summary_md, write_qa_md, write_glossary_md, write_translate_md,
)


@click.group()
@click.version_option(version="0.1.0", prog_name="paperforge")
def cli():
    """PaperForge — PDF to structured knowledge base CLI tool."""
    pass


@cli.command()
@click.argument("pdf", type=click.Path(exists=True, path_type=Path))
@click.option("--vault", required=True, type=click.Path(path_type=Path), help="Obsidian vault path")
@click.option("--no-llm", is_flag=True, default=False, help="Skip LLM generation")
@click.option("--translate", type=click.Choice(["off", "abstract", "full"]), default="off", help="Translation mode")
def ingest(pdf: Path, vault: Path, no_llm: bool, translate: str):
    """Ingest a PDF into the knowledge base."""
    from paperforge.pipeline import ingest as run_ingest

    click.echo(f"Ingesting: {pdf.name}")
    click.echo(f"Vault:     {vault}")

    result = run_ingest(
        pdf_path=pdf,
        vault=vault,
        no_llm=no_llm,
        translate=translate,
    )

    if result.status == "completed":
        click.echo(click.style(f"  OK: {result.message}", fg="green"))
        click.echo(f"  Parser: {result.parser_used} (fallback={result.fallback_used})")
        click.echo(f"  Output: {result.paper_dir}")
    elif result.status == "duplicate":
        click.echo(click.style(f"  SKIP: {result.message}", fg="yellow"))
    else:
        click.echo(click.style(f"  FAIL: {result.message}", fg="red"))
        sys.exit(1)


@cli.command()
@click.option("--vault", required=True, type=click.Path(path_type=Path), help="Obsidian vault path")
@click.option("--fix", is_flag=True, default=False, help="Auto-fix missing directories and config")
def doctor(vault: Path, fix: bool):
    """Check environment, config, and dependencies."""
    from paperforge.config import create_default_config

    checks = []

    # 1. Vault exists
    vault_ok = vault.exists() and vault.is_dir()
    if not vault_ok and fix:
        vault.mkdir(parents=True, exist_ok=True)
        vault_ok = True
        click.echo(click.style("  Created vault directory", fg="green"))
    checks.append(("Vault directory", vault_ok, str(vault)))

    # 2. Config exists
    config_dir = vault / "paperforge"
    config_path = config_dir / "config.yaml"
    config_exists = config_path.exists()
    if not config_exists and fix:
        create_default_config(vault)
        config_exists = True
        click.echo(click.style("  Created default config.yaml", fg="green"))
    checks.append(("Config file", config_exists, str(config_path)))

    # 3. SQLite exists
    db_path = vault / "paperforge" / "paperforge.db"
    db_exists = db_path.exists()
    checks.append(("SQLite database", db_exists, str(db_path)))

    # 4. SQLite schema (if db exists)
    schema_ok = False
    if db_exists:
        try:
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cursor.fetchall()}
            conn.close()
            required = {"papers", "paper_tasks", "references_raw", "reference_candidates", "citation_edges"}
            schema_ok = required.issubset(tables)
            checks.append(("SQLite schema", schema_ok, f"tables: {', '.join(sorted(tables))}"))
        except Exception as e:
            checks.append(("SQLite schema", False, str(e)))
    else:
        checks.append(("SQLite schema", False, "database not found"))

    # 5. Docling installed
    try:
        import docling
        checks.append(("Docling", True, "installed"))
    except ImportError:
        checks.append(("Docling", False, "not installed (pip install docling)"))

    # 6. PyMuPDF installed
    try:
        import fitz
        checks.append(("PyMuPDF", True, "installed"))
    except ImportError:
        checks.append(("PyMuPDF", False, "not installed (pip install pymupdf)"))

    # 7. pdfplumber installed
    try:
        import pdfplumber
        checks.append(("pdfplumber", True, "installed"))
    except ImportError:
        checks.append(("pdfplumber", False, "not installed (pip install pdfplumber)"))

    # 8. langdetect installed
    try:
        import langdetect
        checks.append(("langdetect", True, "installed"))
    except ImportError:
        checks.append(("langdetect", False, "not installed (pip install langdetect)"))

    # 9. rapidfuzz installed
    try:
        import rapidfuzz
        checks.append(("rapidfuzz", True, "installed"))
    except ImportError:
        checks.append(("rapidfuzz", False, "not installed (pip install rapidfuzz)"))

    # 10. Env vars — detect all available providers
    from paperforge.config import detect_providers, KNOWN_PROVIDERS
    detected = detect_providers()
    if detected:
        for provider, key_env, url_env, model, base_url in detected:
            checks.append((f"ENV {key_env}", True, f"({provider}) {model}"))
    else:
        checks.append(("ENV API Key", False, "no API key found in environment"))
    # Also check if config has a provider set
    config_provider = "not set"
    if config_path.exists():
        import yaml as _yaml
        try:
            with io.open(str(config_path)) as _f:
                _data = _yaml.safe_load(_f) or {}
            _llm = _data.get("llm", {})
            config_provider = f"{_llm.get('provider', '?')} / {_llm.get('model', '?')}"
        except Exception:
            pass
    checks.append(("Config LLM provider", config_provider != "not set", config_provider))

    # 11. Database statistics (if db exists)
    paper_count = 0
    pending_count = 0
    failed_count = 0
    if db_exists:
        try:
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT COUNT(*) as cnt FROM papers").fetchone()
            paper_count = row["cnt"] if row else 0

            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM reference_candidates WHERE status = 'pending'"
            ).fetchone()
            pending_count = row["cnt"] if row else 0

            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM paper_tasks WHERE status = 'failed'"
            ).fetchone()
            failed_count = row["cnt"] if row else 0

            conn.close()
        except Exception:
            pass

    checks.append(("Papers in database", paper_count > 0, str(paper_count)))
    if pending_count > 0:
        checks.append(("Pending citations", False, str(pending_count)))
    if failed_count > 0:
        checks.append(("Failed tasks", False, str(failed_count)))

    # Print results
    click.echo("PaperForge Doctor")
    click.echo("=" * 60)
    all_ok = True
    for name, ok, detail in checks:
        icon = click.style("OK", fg="green") if ok else click.style("MISSING", fg="red")
        if not ok:
            # Some checks are optional
            if name in ("Config file", "SQLite database", "SQLite schema",
                        "ENV DEEPSEEK_API_KEY", "ENV DEEPSEEK_BASE_URL",
                        "Papers in database", "Pending citations"):
                icon = click.style("WARN", fg="yellow")
            else:
                all_ok = False
        click.echo(f"  [{icon}] {name}: {detail}")

    click.echo()
    if all_ok:
        click.echo(click.style("All checks passed!", fg="green"))
    else:
        click.echo(click.style("Some required checks failed. See above.", fg="red"))


@cli.command(name="list")
@click.option("--vault", required=True, type=click.Path(path_type=Path), help="Obsidian vault path")
@click.option("--year", type=int, default=None, help="Filter by year")
@click.option("--status", "status_filter", type=str, default=None, help="Filter by status")
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.option("--limit", type=int, default=None, help="Limit number of results")
@click.option("--sort", type=click.Choice(["year", "title"]), default="year", help="Sort field")
def list_papers(vault: Path, year: int | None, status_filter: str | None, fmt: str, limit: int | None, sort: str):
    """List all ingested papers."""
    config = load_config(vault)
    if not config.db_path.exists():
        if fmt == "json":
            click.echo("[]")
        else:
            click.echo("No papers found (database does not exist).")
        return

    conn = db.init_db(config.db_path)
    papers = db.list_papers(conn)
    conn.close()

    if not papers:
        if fmt == "json":
            click.echo("[]")
        else:
            click.echo("No papers found.")
        return

    # Apply filters
    if year is not None:
        papers = [p for p in papers if p.get("year") == year]
    if status_filter is not None:
        papers = [p for p in papers if p.get("status") == status_filter]

    if not papers:
        if fmt == "json":
            click.echo("[]")
        else:
            click.echo("No papers match the given filters.")
        return

    # Sort
    if sort == "title":
        papers.sort(key=lambda p: (p.get("title") or "").lower())
    else:  # year
        papers.sort(key=lambda p: -(p.get("year") or 0))

    # Limit
    if limit is not None:
        papers = papers[:limit]

    # JSON output
    if fmt == "json":
        import json
        output = []
        for p in papers:
            output.append({
                "slug": p.get("slug", ""),
                "title": p.get("title", ""),
                "year": p.get("year"),
                "venue": p.get("venue", "") or "",
                "status": p.get("status", ""),
                "paper_dir": p.get("paper_dir", "") or "",
            })
        click.echo(json.dumps(output, indent=2))
        return

    # Table header
    col_slug = 40
    col_title = 45
    col_year = 6
    col_venue = 14
    col_parser = 10
    col_status = 10

    header = (
        f"{'Slug':<{col_slug}} "
        f"{'Title':<{col_title}} "
        f"{'Year':<{col_year}} "
        f"{'Venue':<{col_venue}} "
        f"{'Parser':<{col_parser}} "
        f"{'Status':<{col_status}}"
    )
    click.echo(header)
    click.echo("-" * len(header))

    for p in papers:
        slug = (p.get("slug") or "")[:col_slug - 1]
        title = (p.get("title") or "")[:col_title - 1]
        pyear = p.get("year") or ""
        venue = (p.get("venue") or "")[:col_venue - 1]
        parser = (p.get("parser") or "")[:col_parser - 1]
        status = (p.get("status") or "")[:col_status - 1]

        # Color code status
        status_color = {
            "completed": "green",
            "partial": "yellow",
            "failed": "red",
            "llm_failed": "red",
        }.get(status, "white")
        status_str = click.style(status, fg=status_color)

        click.echo(
            f"{slug:<{col_slug}} "
            f"{title:<{col_title}} "
            f"{str(pyear):<{col_year}} "
            f"{venue:<{col_venue}} "
            f"{parser:<{col_parser}} "
            f"{status_str}"
        )

    click.echo(f"\nTotal: {len(papers)} papers")


@cli.command()
@click.argument("slug")
@click.option("--vault", required=True, type=click.Path(path_type=Path), help="Obsidian vault path")
def info(slug: str, vault: Path):
    """Show details for a specific paper."""
    config = load_config(vault)
    if not config.db_path.exists():
        click.echo("Database does not exist.")
        return

    conn = db.init_db(config.db_path)
    paper = db.get_paper_by_slug(conn, slug)

    if not paper:
        click.echo(f"Paper not found: {slug}")
        conn.close()
        return

    paper_id = paper["id"]
    click.echo(f"Paper: {paper.get('title', '')}")
    click.echo("=" * 60)

    # Metadata
    click.echo("\nMetadata:")
    for key in ["id", "slug", "authors", "year", "venue", "doi", "language",
                "parser", "parse_quality", "fallback_used", "status",
                "pdf_path", "pdf_sha256", "vault_path", "paper_dir",
                "processed_at", "updated_at"]:
        val = paper.get(key, "")
        click.echo(f"  {key}: {val}")

    # Tasks
    tasks = db.get_tasks_for_paper(conn, paper_id)
    click.echo(f"\nTask Statuses ({len(tasks)}):")
    click.echo(f"  {'Task Type':<15} {'Status':<12} {'Output Path'}")
    click.echo(f"  {'-' * 55}")
    task_types = ["parse", "metadata", "summary", "qa", "glossary", "translate", "references", "link", "index"]
    task_map = {t["task_type"]: t for t in tasks}
    for tt in task_types:
        t = task_map.get(tt)
        if t:
            status_str = t.get("status", "")
            output = t.get("output_path") or ""
            click.echo(f"  {tt:<15} {status_str:<12} {output}")
        else:
            click.echo(f"  {tt:<15} {'n/a':<12}")

    # Also show any task types not in the standard list
    for t in tasks:
        if t["task_type"] not in task_types:
            status_str = t.get("status", "")
            output = t.get("output_path") or ""
            click.echo(f"  {t['task_type']:<15} {status_str:<12} {output}")

    # Citation summary
    citing = db.get_citing_papers(conn, paper_id)
    cited_by = db.get_cited_by_papers(conn, paper_id)
    pending = db.get_pending_candidates(conn)
    pending_for_paper = [c for c in pending if c.get("source_paper_id") == paper_id]

    click.echo(f"\nCitation Summary:")
    click.echo(f"  Cites {len(citing)} papers in this library")
    click.echo(f"  Cited by {len(cited_by)} papers in this library")
    click.echo(f"  {len(pending_for_paper)} pending reference(s)")

    # File paths
    paper_dir = vault / (paper.get("paper_dir") or "")
    click.echo(f"\nFiles:")
    for fname in ["paper.md", "index.md", "summary.md", "qa.md", "glossary.md", "translated.md"]:
        fpath = paper_dir / fname
        exists = fpath.exists()
        icon = click.style("OK", fg="green") if exists else click.style("--", fg="yellow")
        click.echo(f"  [{icon}] {fpath}")

    figures_dir = paper_dir / "figures"
    if figures_dir.exists():
        figs = list(figures_dir.iterdir())
        click.echo(f"  [  ] {figures_dir}/ ({len(figs)} files)")

    conn.close()


@cli.command()
@click.argument("slug")
@click.option("--vault", required=True, type=click.Path(path_type=Path), help="Obsidian vault path")
@click.option("--type", "task_type", required=True,
              type=click.Choice(["summary", "qa", "glossary", "translate"]),
              help="Which LLM task to regenerate")
@click.option("--translate", type=click.Choice(["off", "abstract", "full"]), default="abstract",
              help="Translation mode (only for --type translate)")
def regenerate(slug: str, vault: Path, task_type: str, translate: str):
    """Regenerate a specific LLM output for a paper."""
    config = load_config(vault)
    if not config.db_path.exists():
        click.echo("Database does not exist.")
        sys.exit(1)

    conn = db.init_db(config.db_path)
    paper = db.get_paper_by_slug(conn, slug)
    if not paper:
        click.echo(f"Paper not found: {slug}")
        conn.close()
        sys.exit(1)

    # Read paper.md
    paper_dir = vault / (paper.get("paper_dir") or "")
    paper_md = paper_dir / "paper.md"
    if not paper_md.exists():
        click.echo(f"paper.md not found at {paper_md}")
        conn.close()
        sys.exit(1)

    paper_text = paper_md.read_text(encoding="utf-8")
    year = paper.get("year", 2026)
    title = paper.get("title", slug)

    from paperforge.llm.client import LLMClient
    try:
        llm_client = LLMClient(config.llm)
    except ValueError as e:
        click.echo(click.style(f"  FAIL: {e}", fg="red"))
        conn.close()
        sys.exit(1)

    click.echo(f"Regenerating {task_type} for '{title}'...")

    task_id = db.insert_task(conn, paper["id"], task_type)
    db.update_task_status(conn, task_id, "running")

    try:
        if task_type == "summary":
            from paperforge.generate.summarizer import generate_summary
            result = generate_summary(paper_text, llm_client)
            path = write_summary_md(vault, year, slug, title, result)
        elif task_type == "qa":
            from paperforge.generate.qa_generator import generate_qa
            result = generate_qa(paper_text, llm_client)
            path = write_qa_md(vault, year, slug, title, result)
        elif task_type == "glossary":
            from paperforge.generate.glossary import generate_glossary
            result = generate_glossary(paper_text, llm_client)
            path = write_glossary_md(vault, year, slug, title, result)
        elif task_type == "translate":
            from paperforge.generate.translator import translate_paper
            result = translate_paper(paper_text, llm_client, mode=translate,
                                     chunk_size=config.translation.chunk_size)
            path = write_translate_md(vault, year, slug, result)

        db.update_task_status(conn, task_id, "completed", output_path=str(path))
        click.echo(click.style(f"  OK: {task_type} written to {path}", fg="green"))
    except Exception as e:
        db.update_task_status(conn, task_id, "failed", error=str(e))
        click.echo(click.style(f"  FAIL: {e}", fg="red"))
        conn.close()
        sys.exit(1)

    conn.close()


@cli.command()
@click.argument("slug")
@click.option("--vault", required=True, type=click.Path(path_type=Path), help="Obsidian vault path")
def status(slug: str, vault: Path):
    """Show task statuses for a paper."""
    config = load_config(vault)
    if not config.db_path.exists():
        click.echo("Database does not exist.")
        return

    conn = db.init_db(config.db_path)
    paper = db.get_paper_by_slug(conn, slug)
    if not paper:
        click.echo(f"Paper not found: {slug}")
        conn.close()
        return

    click.echo(f"Paper: {paper.get('title', '')}")
    click.echo(f"Status: {paper.get('status', 'unknown')}")
    click.echo("=" * 60)

    tasks = db.get_tasks_for_paper(conn, paper["id"])
    conn.close()

    if not tasks:
        click.echo("No tasks found.")
        return

    click.echo(f"{'Task Type':<15} {'Status':<12} {'Output Path'}")
    click.echo("-" * 60)
    for t in tasks:
        status_str = t.get("status", "")
        color = {"completed": "green", "failed": "red", "running": "cyan",
                 "skipped": "yellow", "pending": "white"}.get(status_str, "white")
        icon = click.style(status_str, fg=color)
        output = t.get("output_path") or ""
        error = t.get("error") or ""
        click.echo(f"  {t['task_type']:<13} {icon:<22} {output}")
        if error:
            click.echo(f"  {'':13} {click.style('error:', fg='red')} {error[:60]}")


@cli.command()
@click.argument("slug")
@click.option("--vault", required=True, type=click.Path(path_type=Path), help="Obsidian vault path")
@click.option("--translate", type=click.Choice(["off", "abstract", "full"]), default="abstract",
              help="Translation mode for retry")
def retry(slug: str, vault: Path, translate: str):
    """Retry all failed LLM tasks for a paper."""
    config = load_config(vault)
    if not config.db_path.exists():
        click.echo("Database does not exist.")
        sys.exit(1)

    conn = db.init_db(config.db_path)
    paper = db.get_paper_by_slug(conn, slug)
    if not paper:
        click.echo(f"Paper not found: {slug}")
        conn.close()
        sys.exit(1)

    tasks = db.get_tasks_for_paper(conn, paper["id"])
    failed_tasks = [t for t in tasks if t["status"] == "failed"]

    if not failed_tasks:
        click.echo("No failed tasks to retry.")
        conn.close()
        return

    click.echo(f"Retrying {len(failed_tasks)} failed task(s) for '{paper.get('title', slug)}'...")

    # Read paper text
    paper_dir = vault / (paper.get("paper_dir") or "")
    paper_md = paper_dir / "paper.md"
    if not paper_md.exists():
        click.echo(f"paper.md not found at {paper_md}")
        conn.close()
        sys.exit(1)

    paper_text = paper_md.read_text(encoding="utf-8")
    year = paper.get("year", 2026)
    title = paper.get("title", slug)

    from paperforge.llm.client import LLMClient
    try:
        llm_client = LLMClient(config.llm)
    except ValueError as e:
        click.echo(click.style(f"  FAIL: {e}", fg="red"))
        conn.close()
        sys.exit(1)

    retried = 0
    for task in failed_tasks:
        task_type = task["task_type"]
        click.echo(f"  Retrying {task_type}...")

        # Insert new task (don't reuse old one)
        new_task_id = db.insert_task(conn, paper["id"], task_type)
        db.update_task_status(conn, new_task_id, "running")

        try:
            if task_type == "summary":
                from paperforge.generate.summarizer import generate_summary
                result = generate_summary(paper_text, llm_client)
                path = write_summary_md(vault, year, slug, title, result)
            elif task_type == "qa":
                from paperforge.generate.qa_generator import generate_qa
                result = generate_qa(paper_text, llm_client)
                path = write_qa_md(vault, year, slug, title, result)
            elif task_type == "glossary":
                from paperforge.generate.glossary import generate_glossary
                result = generate_glossary(paper_text, llm_client)
                path = write_glossary_md(vault, year, slug, title, result)
            elif task_type == "translate":
                from paperforge.generate.translator import translate_paper
                result = translate_paper(paper_text, llm_client, mode=translate,
                                         chunk_size=config.translation.chunk_size)
                path = write_translate_md(vault, year, slug, result)
            else:
                click.echo(f"    Unknown task type: {task_type}")
                db.update_task_status(conn, new_task_id, "failed", error="Unknown task type")
                continue

            db.update_task_status(conn, new_task_id, "completed", output_path=str(path))
            click.echo(click.style(f"    OK: {task_type}", fg="green"))
            retried += 1
        except Exception as e:
            db.update_task_status(conn, new_task_id, "failed", error=str(e))
            click.echo(click.style(f"    FAIL: {e}", fg="red"))

    # Update paper status
    all_tasks = db.get_tasks_for_paper(conn, paper["id"])
    completed = sum(1 for t in all_tasks if t["status"] in ("completed", "skipped"))
    if completed == len(all_tasks):
        db.update_paper_status(conn, paper["id"], "completed")
    elif completed > 0:
        db.update_paper_status(conn, paper["id"], "partial")

    conn.close()
    click.echo(f"\nRetried {retried}/{len(failed_tasks)} tasks successfully.")


@cli.command()
@click.option("--vault", required=True, type=click.Path(path_type=Path), help="Obsidian vault path")
def relink(vault: Path):
    """Re-scan all papers' references and re-match against the library."""
    config = load_config(vault)
    if not config.db_path.exists():
        click.echo("Database does not exist.")
        sys.exit(1)

    conn = db.init_db(config.db_path)
    papers = db.list_papers(conn)

    if not papers:
        click.echo("No papers found.")
        conn.close()
        return

    click.echo(f"Re-linking {len(papers)} papers...")

    from paperforge.link.references import find_references_section, extract_raw_references
    from paperforge.link.matcher import match_reference, normalize_title
    from paperforge.link.linker import (
        generate_citation_section, update_index_md,
        update_cited_papers_index, update_citing_papers_index,
    )
    from datetime import datetime, timezone
    from uuid import uuid4
    import json as _json

    total_stats = {"confirmed": 0, "pending": 0, "unmatched": 0, "papers": 0}
    now = datetime.now(timezone.utc).isoformat()

    for paper in papers:
        paper_id = paper["id"]
        slug = paper["slug"]
        year = paper.get("year", 2026)

        # Read paper.md
        paper_dir = vault / (paper.get("paper_dir") or "")
        paper_md = paper_dir / "paper.md"
        if not paper_md.exists():
            click.echo(f"  {slug}: paper.md not found, skipping")
            continue

        paper_text = paper_md.read_text(encoding="utf-8")

        # Clear existing references for this paper
        conn.execute("DELETE FROM citation_edges WHERE source_paper_id = ?", (paper_id,))
        conn.execute("DELETE FROM reference_candidates WHERE source_paper_id = ?", (paper_id,))
        conn.execute("DELETE FROM references_raw WHERE source_paper_id = ?", (paper_id,))
        conn.commit()

        # Find references
        ref_text = find_references_section(paper_text)
        if not ref_text:
            click.echo(f"  {slug}: no references section")
            continue

        raw_refs = extract_raw_references(ref_text)
        if not raw_refs:
            click.echo(f"  {slug}: no references extracted")
            continue

        click.echo(f"  {slug}: {len(raw_refs)} references found")

        # Match each reference
        for idx, raw in enumerate(raw_refs):
            # Insert raw reference
            ref_id = uuid4().hex
            norm_title_guess = normalize_title(raw[:200])
            conn.execute(
                """INSERT OR IGNORE INTO references_raw
                   (id, source_paper_id, raw_text, normalized_title,
                    sequence_num, extraction_method, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (ref_id, paper_id, raw, norm_title_guess, idx + 1, "relink", now),
            )

            # Try matching (use raw text as title guess)
            ref_dict = {"title": raw[:200], "year": None, "doi": None}
            result = match_reference(ref_dict, conn, config.citation)

            # Insert candidate
            candidate_id = uuid4().hex
            conn.execute(
                """INSERT INTO reference_candidates
                   (id, source_paper_id, raw_reference_id, title, normalized_title,
                    match_method, confidence, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    candidate_id, paper_id, ref_id,
                    raw[:200], norm_title_guess,
                    result.match_method, result.confidence, result.status,
                    now, now,
                ),
            )

            if result.status == "confirmed" and result.paper_id:
                conn.execute(
                    """INSERT OR REPLACE INTO citation_edges
                       (source_paper_id, target_paper_id, raw_reference_id,
                        match_method, confidence, confirmed, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (paper_id, result.paper_id, ref_id,
                     result.match_method, result.confidence, 1, now, now),
                )
                total_stats["confirmed"] += 1
            elif result.status == "pending":
                total_stats["pending"] += 1
            else:
                total_stats["unmatched"] += 1

        conn.commit()

        # Update index.md
        try:
            citation_data = generate_citation_section(paper_id, conn)
            from paperforge.store.writer import write_index_md
            write_index_md(
                vault=vault, year=year, slug=slug, paper=paper,
                citing_papers=citation_data["citing_papers"],
                cited_by_papers=citation_data["cited_by_papers"],
                pending_refs=citation_data["pending_refs"],
            )
        except Exception as e:
            click.echo(f"    Warning: failed to update index.md: {e}")

        total_stats["papers"] += 1

    # Update all affected papers' index.md
    try:
        for paper in papers:
            update_cited_papers_index(vault, paper["id"], conn)
            update_citing_papers_index(vault, paper["id"], conn)
    except Exception as e:
        click.echo(f"  Warning: failed to update related papers: {e}")

    conn.close()
    click.echo()
    click.echo(f"Re-linking complete: {total_stats['papers']} papers processed")
    click.echo(f"  {total_stats['confirmed']} confirmed, {total_stats['pending']} pending, {total_stats['unmatched']} unmatched")


@cli.command("confirm-ref")
@click.argument("source_slug")
@click.argument("target_slug")
@click.option("--vault", required=True, type=click.Path(path_type=Path), help="Obsidian vault path")
def confirm_ref(source_slug: str, target_slug: str, vault: Path):
    """Confirm a pending citation reference."""
    config = load_config(vault)
    if not config.db_path.exists():
        click.echo("Database does not exist.")
        sys.exit(1)

    conn = db.init_db(config.db_path)

    source = db.get_paper_by_slug(conn, source_slug)
    target = db.get_paper_by_slug(conn, target_slug)

    if not source:
        click.echo(f"Source paper not found: {source_slug}")
        conn.close()
        sys.exit(1)
    if not target:
        click.echo(f"Target paper not found: {target_slug}")
        conn.close()
        sys.exit(1)

    # Find pending candidates that match
    candidates = conn.execute(
        """SELECT * FROM reference_candidates
           WHERE source_paper_id = ? AND status = 'pending'""",
        (source["id"],),
    ).fetchall()

    # Try to find a candidate whose title matches target
    confirmed = False
    for cand in candidates:
        cand_dict = dict(cand)
        if cand_dict.get("normalized_title") and target.get("normalized_title"):
            from rapidfuzz import fuzz
            score = fuzz.ratio(cand_dict["normalized_title"], target["normalized_title"])
            if score >= 80:
                db.update_candidate_status(conn, cand_dict["id"], "confirmed")
                db.insert_citation_edge(
                    conn, source["id"], target["id"],
                    match_method="manual", confidence=1.0,
                )
                conn.execute(
                    "UPDATE reference_candidates SET matched_paper_id = ? WHERE id = ?",
                    (target["id"], cand_dict["id"]),
                )
                conn.commit()
                confirmed = True
                click.echo(click.style(f"  Confirmed: {source_slug} -> {target_slug}", fg="green"))
                break

    if not confirmed:
        db.insert_citation_edge(
            conn, source["id"], target["id"],
            match_method="manual", confidence=1.0,
        )
        click.echo(click.style(f"  Created citation: {source_slug} -> {target_slug}", fg="green"))

    # Update index.md files
    from paperforge.link.linker import update_index_md, update_cited_papers_index, update_citing_papers_index
    try:
        update_index_md(vault, source, conn)
        update_index_md(vault, target, conn)
    except Exception as e:
        click.echo(f"  Warning: failed to update index.md: {e}")

    conn.close()


@cli.command("reject-ref")
@click.argument("source_slug")
@click.argument("target_slug")
@click.option("--vault", required=True, type=click.Path(path_type=Path), help="Obsidian vault path")
def reject_ref(source_slug: str, target_slug: str, vault: Path):
    """Reject a pending citation reference."""
    config = load_config(vault)
    if not config.db_path.exists():
        click.echo("Database does not exist.")
        sys.exit(1)

    conn = db.init_db(config.db_path)

    source = db.get_paper_by_slug(conn, source_slug)
    target = db.get_paper_by_slug(conn, target_slug)

    if not source:
        click.echo(f"Source paper not found: {source_slug}")
        conn.close()
        sys.exit(1)
    if not target:
        click.echo(f"Target paper not found: {target_slug}")
        conn.close()
        sys.exit(1)

    # Find and reject pending candidates
    candidates = conn.execute(
        """SELECT * FROM reference_candidates
           WHERE source_paper_id = ? AND status = 'pending'""",
        (source["id"],),
    ).fetchall()

    rejected = False
    for cand in candidates:
        cand_dict = dict(cand)
        if cand_dict.get("normalized_title") and target.get("normalized_title"):
            from rapidfuzz import fuzz
            score = fuzz.ratio(cand_dict["normalized_title"], target["normalized_title"])
            if score >= 80:
                db.update_candidate_status(conn, cand_dict["id"], "rejected")
                rejected = True
                click.echo(click.style(f"  Rejected: {source_slug} !-> {target_slug}", fg="yellow"))
                break

    if not rejected:
        click.echo("  No matching pending reference found to reject.")

    # Delete any existing edge
    db.delete_citation_edge(conn, source["id"], target["id"])

    # Update index.md files
    from paperforge.link.linker import update_index_md
    try:
        update_index_md(vault, source, conn)
        update_index_md(vault, target, conn)
    except Exception as e:
        click.echo(f"  Warning: failed to update index.md: {e}")

    conn.close()


# ============================================================
# MVP 4 — New CLI commands
# ============================================================


@cli.command()
@click.argument("slug")
@click.option("--vault", required=True, type=click.Path(path_type=Path), help="Obsidian vault path")
@click.option("--yes", "-y", is_flag=True, default=False, help="Skip confirmation prompt")
def remove(slug: str, vault: Path, yes: bool):
    """Remove a paper from the knowledge base."""
    config = load_config(vault)
    if not config.db_path.exists():
        click.echo("Database does not exist.")
        sys.exit(1)

    conn = db.init_db(config.db_path)
    paper = db.get_paper_by_slug(conn, slug)
    if not paper:
        click.echo(f"Paper not found: {slug}")
        conn.close()
        sys.exit(1)

    paper_id = paper["id"]
    paper_dir = vault / (paper.get("paper_dir") or "")
    title = paper.get("title", slug)

    # Show what will be deleted
    click.echo(f"Paper: {title}")
    click.echo(f"  ID:   {paper_id}")
    click.echo(f"  Dir:  {paper_dir}")

    # Count related records
    tasks = db.get_tasks_for_paper(conn, paper_id)
    refs = conn.execute(
        "SELECT COUNT(*) as cnt FROM references_raw WHERE source_paper_id = ?",
        (paper_id,),
    ).fetchone()
    candidates = conn.execute(
        "SELECT COUNT(*) as cnt FROM reference_candidates WHERE source_paper_id = ?",
        (paper_id,),
    ).fetchone()
    edges_out = conn.execute(
        "SELECT COUNT(*) as cnt FROM citation_edges WHERE source_paper_id = ?",
        (paper_id,),
    ).fetchone()
    edges_in = conn.execute(
        "SELECT COUNT(*) as cnt FROM citation_edges WHERE target_paper_id = ?",
        (paper_id,),
    ).fetchone()

    click.echo(f"  Tasks:       {len(tasks)}")
    click.echo(f"  References:  {refs['cnt'] if refs else 0}")
    click.echo(f"  Candidates:  {candidates['cnt'] if candidates else 0}")
    click.echo(f"  Edges (out): {edges_out['cnt'] if edges_out else 0}")
    click.echo(f"  Edges (in):  {edges_in['cnt'] if edges_in else 0}")

    if not yes:
        click.confirm(
            click.style(f"\nAre you sure you want to remove '{title}'?", fg="red"),
            abort=True,
        )

    # 1. Delete from SQLite (in correct order for foreign keys)
    conn.execute("DELETE FROM citation_edges WHERE source_paper_id = ? OR target_paper_id = ?",
                 (paper_id, paper_id))
    conn.execute("DELETE FROM reference_candidates WHERE source_paper_id = ?", (paper_id,))
    conn.execute("DELETE FROM references_raw WHERE source_paper_id = ?", (paper_id,))
    conn.execute("DELETE FROM paper_tasks WHERE paper_id = ?", (paper_id,))
    conn.execute("DELETE FROM papers WHERE id = ?", (paper_id,))
    conn.commit()

    # 2. Delete paper directory
    if paper_dir.exists():
        shutil.rmtree(paper_dir)
        click.echo(f"  Deleted directory: {paper_dir}")
    else:
        click.echo(f"  Directory not found: {paper_dir}")

    # 3. Regenerate papers/index.md
    remaining = db.list_papers(conn)
    from paperforge.store.writer import write_papers_index
    write_papers_index(vault, remaining)

    # 4. Update other papers' index.md that referenced this paper
    try:
        from paperforge.link.linker import update_index_md
        for p in remaining:
            update_index_md(vault, p, conn)
    except Exception as e:
        click.echo(f"  Warning: failed to update related indexes: {e}")

    conn.close()
    click.echo(click.style(f"\n  Removed: '{title}' ({slug})", fg="green"))


@cli.command("rebuild-index")
@click.option("--vault", required=True, type=click.Path(path_type=Path), help="Obsidian vault path")
def rebuild_index(vault: Path):
    """Regenerate all index.md files from database."""
    config = load_config(vault)
    if not config.db_path.exists():
        click.echo("Database does not exist.")
        sys.exit(1)

    conn = db.init_db(config.db_path)
    papers = db.list_papers(conn)

    if not papers:
        click.echo("No papers found.")
        conn.close()
        return

    click.echo(f"Rebuilding indexes for {len(papers)} papers...")

    from paperforge.store.writer import write_papers_index, write_index_md
    from paperforge.link.linker import generate_citation_section

    # 1. Regenerate papers/index.md
    write_papers_index(vault, papers)
    click.echo(f"  Regenerated papers/index.md")

    # 2. Regenerate each paper's index.md
    updated = 0
    for paper in papers:
        try:
            year = paper.get("year", 2026)
            slug = paper["slug"]
            paper_id = paper["id"]

            citation_data = generate_citation_section(paper_id, conn)
            write_index_md(
                vault=vault, year=year, slug=slug, paper=paper,
                citing_papers=citation_data["citing_papers"],
                cited_by_papers=citation_data["cited_by_papers"],
                pending_refs=citation_data["pending_refs"],
            )
            updated += 1
        except Exception as e:
            click.echo(click.style(f"  FAIL: {paper['slug']}: {e}", fg="red"))

    conn.close()
    click.echo(click.style(f"\n  Rebuilt {updated}/{len(papers)} index files.", fg="green"))


@cli.command()
@click.argument("slug")
@click.option("--vault", required=True, type=click.Path(path_type=Path), help="Obsidian vault path")
def open(slug: str, vault: Path):
    """Open a paper's index.md in the system default application."""
    config = load_config(vault)
    if not config.db_path.exists():
        click.echo("Database does not exist.")
        sys.exit(1)

    conn = db.init_db(config.db_path)
    paper = db.get_paper_by_slug(conn, slug)
    conn.close()

    if not paper:
        click.echo(f"Paper not found: {slug}")
        sys.exit(1)

    paper_dir = vault / (paper.get("paper_dir") or "")
    index_path = paper_dir / "index.md"

    if not index_path.exists():
        click.echo(f"index.md not found at {index_path}")
        sys.exit(1)

    click.echo(f"Opening: {index_path}")
    click.launch(str(index_path), locate=False)


@cli.command(name="export")
@click.option("--vault", required=True, type=click.Path(path_type=Path), help="Obsidian vault path")
@click.option("--format", "fmt", type=click.Choice(["zip"]), default="zip", help="Export format")
@click.option("--output", "-o", type=click.Path(path_type=Path), default=None,
              help="Output file path (default: vault/paperforge-export-{timestamp}.zip)")
def export_cmd(vault: Path, fmt: str, output: Path | None):
    """Export the knowledge base as a zip archive."""
    papers_dir = vault / "papers"
    db_path = vault / "paperforge" / "paperforge.db"

    if not papers_dir.exists() and not db_path.exists():
        click.echo("Nothing to export (no papers directory or database found).")
        sys.exit(1)

    # Determine output path
    if output is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output = vault / f"paperforge-export-{timestamp}.zip"

    click.echo(f"Exporting to: {output}")

    import zipfile

    with zipfile.ZipFile(str(output), "w", zipfile.ZIP_DEFLATED) as zf:
        # Add papers directory
        if papers_dir.exists():
            for fpath in papers_dir.rglob("*"):
                if fpath.is_file():
                    arcname = f"papers/{fpath.relative_to(papers_dir)}"
                    zf.write(fpath, arcname)
            click.echo(f"  Added papers/ ({sum(1 for _ in papers_dir.rglob('*') if _.is_file())} files)")

        # Add database
        if db_path.exists():
            zf.write(db_path, "paperforge.db")
            click.echo(f"  Added paperforge.db")

        # Add config if present
        config_path = vault / "paperforge" / "config.yaml"
        if config_path.exists():
            zf.write(config_path, "config.yaml")
            click.echo(f"  Added config.yaml")

    size_mb = output.stat().st_size / (1024 * 1024)
    click.echo(click.style(f"\n  Export complete: {output} ({size_mb:.1f} MB)", fg="green"))


@cli.command("config")
@click.option("--vault", required=True, type=click.Path(path_type=Path), help="Obsidian vault path")
def config_cmd(vault: Path):
    """Auto-detect API keys and configure LLM provider."""
    from paperforge.config import detect_providers, get_provider_config, create_default_config

    click.echo("Scanning environment for API keys...\n")

    detected = detect_providers()

    if not detected:
        click.echo(click.style("  No API keys found in environment.", fg="yellow"))
        click.echo("\n  Set an API key first, e.g.:")
        click.echo('    export DEEPSEEK_API_KEY="sk-xxxxxxxx"    # Linux/macOS')
        click.echo('    $env:DEEPSEEK_API_KEY = "sk-xxxxxxxx"   # Windows PowerShell')
        click.echo('    set DEEPSEEK_API_KEY=sk-xxxxxxxx         # Windows CMD')
        sys.exit(1)

    # Show detected providers
    click.echo(click.style("  Detected providers:", fg="green"))
    for i, (provider, key_env, url_env, model, base_url) in enumerate(detected, 1):
        key_val = os.environ.get(key_env, "")
        masked = key_val[:8] + "..." + key_val[-4:] if len(key_val) > 12 else "***"
        click.echo(f"    [{i}] {provider:<15} model={model:<30} key={masked}")

    # Let user choose
    if len(detected) == 1:
        chosen = detected[0]
        click.echo(f"\n  Only one provider found: {chosen[0]}")
    else:
        click.echo("")
        while True:
            try:
                choice = click.prompt("  Select provider number", type=int)
                if 1 <= choice <= len(detected):
                    chosen = detected[choice - 1]
                    break
                click.echo(click.style(f"  Enter 1-{len(detected)}", fg="red"))
            except (ValueError, click.Abort):
                click.echo(click.style(f"  Enter 1-{len(detected)}", fg="red"))

    provider, key_env, url_env, model, default_base_url = chosen
    click.echo(f"\n  Selected: {provider}")

    # Fetch available models from the API
    api_key = os.environ.get(key_env, "")
    base_url = os.environ.get(url_env, "") or default_base_url
    click.echo(f"  Fetching models from {base_url}...")

    from paperforge.config import fetch_models
    available_models = fetch_models(api_key, base_url)

    if available_models:
        click.echo(click.style(f"  Found {len(available_models)} models:\n", fg="green"))
        for i, m in enumerate(available_models, 1):
            click.echo(f"    [{i}] {m['id']}")

        click.echo(f"\n  Default (from config): {model}")
        click.echo("  Press Enter to use default, or enter model number\n")

        while True:
            try:
                model_input = click.prompt("  Model selection", default="", show_default=False)
                if model_input == "":
                    # Use default
                    break
                model_idx = int(model_input)
                if 1 <= model_idx <= len(available_models):
                    model = available_models[model_idx - 1]["id"]
                    break
                click.echo(click.style(f"  Enter 1-{len(available_models)} or Enter for default", fg="red"))
            except (ValueError, click.Abort):
                click.echo(click.style(f"  Enter 1-{len(available_models)} or Enter for default", fg="red"))
    else:
        click.echo(click.style("  Could not fetch model list (using default)", fg="yellow"))
        custom = click.prompt(f"  Model name", default=model, show_default=True)
        if custom:
            model = custom

    click.echo(f"\n  Model: {model}")

    # Ask: one-time or default?
    click.echo("\n  [1] Only use this time (don't save)")
    click.echo("  [2] Set as default (save to config.yaml)")
    click.echo("")

    while True:
        try:
            save_choice = click.prompt("  Your choice", type=int)
            if save_choice in (1, 2):
                break
            click.echo(click.style("  Enter 1 or 2", fg="red"))
        except (ValueError, click.Abort):
            click.echo(click.style("  Enter 1 or 2", fg="red"))

    if save_choice == 1:
        # One-time: just set env vars for this process (already set by user)
        click.echo(click.style(f"\n  Using {provider} for this session only.", fg="green"))
        click.echo(f"  Config not modified. API key from environment: {key_env}")
    else:
        # Save to config.yaml
        config_dir = vault / "paperforge"
        config_path = config_dir / "config.yaml"
        config_dir.mkdir(parents=True, exist_ok=True)

        # Load existing or create new
        if config_path.exists():
            with io.open(str(config_path)) as f:
                data = yaml.safe_load(f) or {}
        else:
            data = {}

        # Update LLM section
        base_url_env = url_env if os.environ.get(url_env) else ""
        data["llm"] = {
            "provider": provider,
            "model": model,
            "api_key_env": key_env,
            "base_url_env": base_url_env,
            "timeout_seconds": data.get("llm", {}).get("timeout_seconds", 120),
            "max_retries": data.get("llm", {}).get("max_retries", 3),
        }

        with io.open(str(config_path), "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)

        click.echo(click.style(f"\n  Saved to {config_path}", fg="green"))
        click.echo(f"  Provider: {provider}")
        click.echo(f"  Model:    {model}")
        click.echo(f"  Key env:  {key_env}")
        if base_url_env:
            click.echo(f"  URL env:  {base_url_env}")

    click.echo("")


if __name__ == "__main__":
    cli()
