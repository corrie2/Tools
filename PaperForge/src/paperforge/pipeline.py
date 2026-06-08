"""Main ingestion pipeline for PaperForge."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from paperforge.config import Config, load_config
from paperforge.models.paper import Paper, generate_slug, normalize_title
from paperforge.parse.metadata import extract_metadata, compute_pdf_sha256
from paperforge.store import db
from paperforge.store.writer import (
    write_index_md, write_papers_index, write_paper_md,
    write_summary_md, write_qa_md, write_glossary_md, write_translate_md,
)

logger = logging.getLogger(__name__)


@dataclass
class IngestResult:
    """Result of an ingestion pipeline run."""
    paper: Optional[Paper] = None
    status: str = "completed"
    parser_used: str = ""
    fallback_used: bool = False
    message: str = ""
    paper_dir: Optional[Path] = None


def ingest(
    pdf_path: Path,
    vault: Path,
    no_llm: bool = True,
    translate: str = "off",
    config: Optional[Config] = None,
) -> IngestResult:
    """Run the full ingestion pipeline for a single PDF.

    Steps:
    1. Load config
    2. Compute sha256, check for duplicate
    3. Parse PDF (docling -> fallback)
    4. Extract metadata
    5. Generate slug, paper_id
    6. Write paper.md + figures to vault
    7. Write index.md
    8. Insert into SQLite
    9. Update papers/index.md
    10. Return result with status
    """
    # 1. Load config
    if config is None:
        config = load_config(vault)

    # Resolve translate mode: CLI flag overrides config
    if translate == "off" and config.translation.default_mode != "off":
        # If CLI says "off" (the default), use config's default_mode
        translate = config.translation.default_mode

    # Ensure directories exist
    config.data_path.mkdir(parents=True, exist_ok=True)

    # Initialize database
    conn = db.init_db(config.db_path)

    # 2. Compute sha256, check for duplicate
    sha256 = compute_pdf_sha256(pdf_path)
    existing = db.get_paper_by_sha256(conn, sha256)
    if existing:
        return IngestResult(
            status="duplicate",
            message=f"PDF already ingested as '{existing['slug']}' (id={existing['id'][:8]}...)",
        )

    # 3. Parse PDF (docling -> fallback)
    from paperforge.parse.docling_parser import parse_with_docling, ParseResult
    from paperforge.parse.fallback_parser import parse_with_fallback

    # Create a temp output dir for figures during parsing
    temp_dir = config.data_path / "tmp" / sha256[:12]
    temp_dir.mkdir(parents=True, exist_ok=True)

    result: Optional[ParseResult] = None
    fallback_used = False

    # Try docling first
    logger.info("Parsing PDF with Docling...")
    result = parse_with_docling(
        pdf_path,
        output_dir=temp_dir,
        save_figures=config.parser.save_figures,
        save_tables=config.parser.save_tables,
    )

    if result is None:
        logger.info("Docling failed, falling back to PyMuPDF + pdfplumber...")
        result = parse_with_fallback(
            pdf_path,
            output_dir=temp_dir,
            save_figures=config.parser.save_figures,
            save_tables=config.parser.save_tables,
        )
        fallback_used = True

    if result is None:
        return IngestResult(
            status="failed",
            message="Both Docling and fallback parsers failed",
        )

    # 4. Extract metadata
    logger.info("Extracting metadata...")
    meta = extract_metadata(pdf_path)

    # Merge with any metadata from parser
    title = meta.get("title") or ""
    authors = meta.get("authors") or []
    doi = meta.get("doi")
    language = meta.get("language", "unknown")
    venue = ""
    year = datetime.now().year
    external_id = None

    # Use DOI from parsed text if not found in metadata
    if not doi and result.markdown:
        from paperforge.parse.metadata import extract_doi
        doi = extract_doi(result.markdown[:3000])

    # 4b. Enrich metadata via Semantic Scholar (non-blocking on failure)
    try:
        from paperforge.link.semantic_scholar import enrich_metadata
        s2_result = enrich_metadata(doi=doi, title=title)
        if s2_result:
            # Use S2 data to override/enrich local extraction
            s2_title = s2_result.get("title", "")
            if s2_title and len(s2_title) > len(title):
                title = s2_title
            s2_authors = s2_result.get("authors", [])
            if s2_authors:
                authors = s2_authors
            s2_year = s2_result.get("year")
            if s2_year:
                year = s2_year
            s2_venue = s2_result.get("venue", "")
            if s2_venue:
                venue = s2_venue
            s2_doi = s2_result.get("doi")
            if s2_doi and not doi:
                doi = s2_doi
            external_id = s2_result.get("paperId")
            logger.info("Enriched metadata from Semantic Scholar (id=%s)", external_id)
    except Exception as e:
        logger.warning("Semantic Scholar enrichment failed (continuing with local): %s", e)

    # 5. Generate slug, paper_id
    slug = generate_slug(title) if title else generate_slug(pdf_path.stem)
    norm_title = normalize_title(title) if title else ""

    # Determine year (default to current year if unknown)
    from datetime import datetime
    if not year or year == datetime.now().year:
        # If S2 didn't set a year, try to extract from text
        if not year or year == datetime.now().year:
            year = datetime.now().year

    paper = Paper(
        slug=slug,
        title=title,
        normalized_title=norm_title,
        authors=authors,
        year=year,
        venue=venue or None,
        doi=doi,
        language=language,
        pdf_path=str(pdf_path),
        pdf_sha256=sha256,
        parser=result.parser,
        parse_quality=result.quality,
        fallback_used=fallback_used,
        external_id=external_id,
    )

    # Set vault paths
    paper.paper_dir = f"papers/{year}/{slug}"
    paper.vault_path = f"papers/{year}/{slug}/index.md"

    # 6. Write paper.md + figures to vault
    logger.info("Writing paper files to vault...")
    paper_dir = write_paper_md(
        vault=vault,
        year=year,
        slug=slug,
        markdown=result.markdown,
        figures=result.figures if result.figures else None,
    )

    # 7. Write index.md
    logger.info("Writing index.md...")
    write_index_md(
        vault=vault,
        year=year,
        slug=slug,
        paper=paper.model_dump(),
    )

    # 8. Insert into SQLite
    logger.info("Inserting into database...")
    db.insert_paper(conn, paper.to_db_dict())
    task_id = db.insert_task(conn, paper.id, "ingest")
    db.update_task_status(conn, task_id, "running")
    db.update_task_status(conn, task_id, "completed", output_path=paper.vault_path)

    # 9. Update papers/index.md
    logger.info("Updating papers index...")
    all_papers = db.list_papers(conn)
    write_papers_index(vault, all_papers)

    # 10. LLM generation (if not skipped)
    llm_success_count = 0
    llm_total = 0

    if not no_llm:
        logger.info("Running LLM generation steps...")
        llm_success_count, llm_total = _run_llm_steps(
            conn=conn,
            paper_id=paper.id,
            vault=vault,
            year=year,
            slug=slug,
            title=title,
            paper_text=result.markdown,
            translate_mode=translate,
            config=config,
        )
        # Update paper status based on LLM results
        if llm_total > 0:
            if llm_success_count == llm_total:
                db.update_paper_status(conn, paper.id, "completed")
            elif llm_success_count > 0:
                db.update_paper_status(conn, paper.id, "partial")
            else:
                db.update_paper_status(conn, paper.id, "llm_failed")
    else:
        # Mark LLM tasks as skipped
        for task_type in ["summary", "qa", "glossary", "translate"]:
            task_id = db.insert_task(conn, paper.id, task_type)
            db.update_task_status(conn, task_id, "skipped")

    # Clean up temp dir
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)

    # 11. Extract references and build citation graph (always runs, regardless of no_llm)
    _run_reference_linking(conn, paper.id, vault, year, slug, title, result.markdown, config)

    conn.close()

    # Build message
    status = "completed"
    msg = f"Successfully ingested '{title}' ({result.parser}, {result.quality})"
    if not no_llm and llm_total > 0:
        msg += f" [LLM: {llm_success_count}/{llm_total} steps OK]"
        if llm_success_count < llm_total:
            status = "partial"

    return IngestResult(
        paper=paper,
        status=status,
        parser_used=result.parser,
        fallback_used=fallback_used,
        message=msg,
        paper_dir=paper_dir,
    )


def _run_llm_steps(
    conn,
    paper_id: str,
    vault: Path,
    year: int,
    slug: str,
    title: str,
    paper_text: str,
    translate_mode: str,
    config: Config,
) -> tuple[int, int]:
    """Run LLM generation steps (summary, qa, glossary, translate).

    Each step can fail independently without aborting the pipeline.

    Returns:
        (success_count, total_count)
    """
    from paperforge.llm.client import LLMClient
    from paperforge.generate.summarizer import generate_summary
    from paperforge.generate.qa_generator import generate_qa
    from paperforge.generate.glossary import generate_glossary
    from paperforge.generate.translator import translate_paper

    success = 0
    total = 0

    # Create LLM client
    try:
        llm_client = LLMClient(config.llm)
    except ValueError as e:
        logger.error("Cannot create LLM client: %s", e)
        # Mark all tasks as failed
        for task_type in ["summary", "qa", "glossary", "translate"]:
            task_id = db.insert_task(conn, paper_id, task_type)
            db.update_task_status(conn, task_id, "failed", error=str(e))
        return 0, 4

    # --- Summary ---
    total += 1
    task_id = db.insert_task(conn, paper_id, "summary")
    db.update_task_status(conn, task_id, "running")
    try:
        summary = generate_summary(paper_text, llm_client)
        path = write_summary_md(vault, year, slug, title, summary)
        db.update_task_status(conn, task_id, "completed", output_path=str(path))
        success += 1
        logger.info("Summary generated successfully")
    except Exception as e:
        logger.error("Summary generation failed: %s", e)
        db.update_task_status(conn, task_id, "failed", error=str(e))

    # --- Q&A ---
    total += 1
    task_id = db.insert_task(conn, paper_id, "qa")
    db.update_task_status(conn, task_id, "running")
    try:
        qa = generate_qa(paper_text, llm_client)
        path = write_qa_md(vault, year, slug, title, qa)
        db.update_task_status(conn, task_id, "completed", output_path=str(path))
        success += 1
        logger.info("Q&A generated successfully")
    except Exception as e:
        logger.error("Q&A generation failed: %s", e)
        db.update_task_status(conn, task_id, "failed", error=str(e))

    # --- Glossary ---
    total += 1
    task_id = db.insert_task(conn, paper_id, "glossary")
    db.update_task_status(conn, task_id, "running")
    try:
        glossary = generate_glossary(paper_text, llm_client)
        path = write_glossary_md(vault, year, slug, title, glossary)
        db.update_task_status(conn, task_id, "completed", output_path=str(path))
        success += 1
        logger.info("Glossary generated successfully")
    except Exception as e:
        logger.error("Glossary generation failed: %s", e)
        db.update_task_status(conn, task_id, "failed", error=str(e))

    # --- Translate ---
    total += 1
    task_id = db.insert_task(conn, paper_id, "translate")
    db.update_task_status(conn, task_id, "running")
    if translate_mode == "off":
        db.update_task_status(conn, task_id, "skipped")
        success += 1  # Skipped counts as success
    else:
        try:
            translated = translate_paper(
                paper_text, llm_client, mode=translate_mode,
                chunk_size=config.translation.chunk_size,
            )
            path = write_translate_md(vault, year, slug, translated)
            db.update_task_status(conn, task_id, "completed", output_path=str(path))
            success += 1
            logger.info("Translation generated successfully")
        except Exception as e:
            logger.error("Translation failed: %s", e)
            db.update_task_status(conn, task_id, "failed", error=str(e))

    return success, total


def _run_reference_linking(
    conn,
    paper_id: str,
    vault: Path,
    year: int,
    slug: str,
    title: str,
    paper_text: str,
    config: Config,
) -> None:
    """Extract references from paper.md and build citation edges.

    This step always runs (even with --no-llm). It:
    1. Finds the References section in paper.md
    2. Extracts raw reference strings
    3. Matches against existing papers (DOI -> title fuzzy)
    4. Creates citation_edges for confirmed matches
    5. Creates reference_candidates for all references
    6. Updates index.md with citation sections
    7. Updates cited/citing papers' index.md files

    Errors in reference extraction do NOT crash the pipeline.
    """
    from paperforge.link.references import find_references_section, extract_raw_references
    from paperforge.link.matcher import match_reference, normalize_title
    from paperforge.link.linker import (
        generate_citation_section, update_index_md,
        update_cited_papers_index, update_citing_papers_index,
    )
    from datetime import datetime, timezone
    from uuid import uuid4
    import json as _json

    task_id = db.insert_task(conn, paper_id, "references")
    db.update_task_status(conn, task_id, "running")

    try:
        # 1. Find references section
        ref_text = find_references_section(paper_text)
        if not ref_text:
            logger.info("No references section found in paper.md")
            db.update_task_status(conn, task_id, "skipped", error="No references section found")
            return

        # 2. Extract raw references
        raw_refs = extract_raw_references(ref_text)
        if not raw_refs:
            logger.info("No individual references extracted")
            db.update_task_status(conn, task_id, "skipped", error="No references extracted")
            return

        logger.info("Extracted %d raw references", len(raw_refs))

        # 3. Try LLM structuring (optional - fall back to raw matching)
        structured_refs = []
        try:
            from paperforge.llm.client import LLMClient
            from paperforge.link.references import structure_references
            llm_client = LLMClient(config.llm)
            structured_refs = structure_references(raw_refs, llm_client)
            logger.info("Structured %d references via LLM", len(structured_refs))
        except Exception as e:
            logger.warning("LLM structuring failed, using raw refs for matching: %s", e)
            # Create stub structured refs from raw text
            for raw in raw_refs:
                structured_refs.append({
                    "authors": [],
                    "title": raw[:200],  # Use first 200 chars as title guess
                    "year": None,
                    "venue": None,
                    "doi": None,
                    "_raw": raw,
                })

        # 4. Match and create edges
        stats = {"confirmed": 0, "pending": 0, "unmatched": 0}
        now = datetime.now(timezone.utc).isoformat()

        for idx, ref in enumerate(structured_refs):
            try:
                raw_text = ref.get("_raw", ref.get("title", ""))
                parsed_title = ref.get("title", "")
                parsed_authors = ref.get("authors", [])
                parsed_year = ref.get("year")
                parsed_venue = ref.get("venue")
                parsed_doi = ref.get("doi")
                norm_title = normalize_title(parsed_title) if parsed_title else ""

                # Insert raw reference
                ref_id = uuid4().hex
                conn.execute(
                    """INSERT OR IGNORE INTO references_raw
                       (id, source_paper_id, raw_text, parsed_authors, parsed_title,
                        normalized_title, parsed_year, parsed_venue, parsed_doi,
                        sequence_num, extraction_method, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        ref_id, paper_id, raw_text,
                        _json.dumps(parsed_authors) if parsed_authors else None,
                        parsed_title or None, norm_title or None,
                        parsed_year, parsed_venue, parsed_doi,
                        idx + 1, "llm", now,
                    ),
                )

                # Match
                result = match_reference(ref, conn, config.citation)

                # Insert candidate
                candidate_id = uuid4().hex
                conn.execute(
                    """INSERT INTO reference_candidates
                       (id, source_paper_id, raw_reference_id, title, normalized_title,
                        authors, year, venue, doi, matched_paper_id,
                        match_method, confidence, status, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        candidate_id, paper_id, ref_id,
                        parsed_title, norm_title,
                        _json.dumps(parsed_authors) if parsed_authors else None,
                        parsed_year, parsed_venue, parsed_doi,
                        result.paper_id, result.match_method,
                        result.confidence, result.status, now, now,
                    ),
                )

                # Create edge for confirmed
                if result.status == "confirmed" and result.paper_id:
                    conn.execute(
                        """INSERT OR REPLACE INTO citation_edges
                           (source_paper_id, target_paper_id, raw_reference_id,
                            match_method, confidence, confirmed, created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (paper_id, result.paper_id, ref_id,
                         result.match_method, result.confidence, 1, now, now),
                    )
                    stats["confirmed"] += 1
                elif result.status == "pending":
                    stats["pending"] += 1
                else:
                    stats["unmatched"] += 1

            except Exception as e:
                logger.warning("Error processing reference %d: %s", idx, e)

        conn.commit()

        # 5. Update index.md with citation sections
        paper = db.get_paper_by_id(conn, paper_id)
        if paper:
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
                logger.warning("Failed to update index.md with citations: %s", e)

        # 6. Update cited/citing papers' index.md
        if stats["confirmed"] > 0:
            try:
                update_cited_papers_index(vault, paper_id, conn)
                update_citing_papers_index(vault, paper_id, conn)
            except Exception as e:
                logger.warning("Failed to update related papers' index.md: %s", e)

        logger.info(
            "Reference linking: %d confirmed, %d pending, %d unmatched (out of %d)",
            stats["confirmed"], stats["pending"], stats["unmatched"], len(structured_refs),
        )

        db.update_task_status(
            conn, task_id, "completed",
            output_path=f"{stats['confirmed']} confirmed, {stats['pending']} pending, {stats['unmatched']} unmatched",
        )

    except Exception as e:
        logger.error("Reference linking failed: %s", e)
        db.update_task_status(conn, task_id, "failed", error=str(e))
