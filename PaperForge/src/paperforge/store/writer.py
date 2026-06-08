"""File writer — writes paper files and generates index.md from Jinja2 templates."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Dict, List, Optional

from jinja2 import Environment, FileSystemLoader


def _get_template_env() -> Environment:
    """Get Jinja2 environment with templates from the package."""
    template_dir = Path(__file__).parent.parent / "templates"
    return Environment(
        loader=FileSystemLoader(str(template_dir)),
        keep_trailing_newline=True,
    )


def write_paper_md(
    vault: Path,
    year: int | None,
    slug: str,
    markdown: str,
    figures: Optional[Dict[str, Path]] = None,
) -> Path:
    """Write paper.md and copy figures to vault/papers/{year}/{slug}/.

    Args:
        vault: Vault root path.
        year: Publication year.
        slug: Paper slug.
        markdown: Paper markdown content.
        figures: Dict mapping figure filename -> source path.

    Returns:
        Path to the paper directory.
    """
    papers_dir = vault / "papers" / str(year or "unknown") / slug
    papers_dir.mkdir(parents=True, exist_ok=True)

    # Write paper.md
    paper_md_path = papers_dir / "paper.md"
    paper_md_path.write_text(markdown, encoding="utf-8")

    # Copy figures
    if figures:
        fig_dir = papers_dir / "figures"
        fig_dir.mkdir(exist_ok=True)
        for fig_name, fig_src in figures.items():
            if fig_src.exists():
                shutil.copy2(fig_src, fig_dir / fig_name)

    return papers_dir


def write_index_md(
    vault: Path,
    year: int | None,
    slug: str,
    paper: dict,
    tags: Optional[List[str]] = None,
    citing_papers: Optional[List[dict]] = None,
    cited_by_papers: Optional[List[dict]] = None,
    pending_refs: Optional[List[dict]] = None,
    one_sentence_summary: Optional[str] = None,
) -> Path:
    """Generate and write index.md for a paper.

    Args:
        vault: Vault root path.
        year: Publication year.
        slug: Paper slug.
        paper: Paper dict with title, authors, year, venue, doi, etc.
        tags: Additional tags for YAML frontmatter.
        citing_papers: Papers this paper cites (with slug, method, confidence).
        cited_by_papers: Papers that cite this paper.
        pending_refs: References awaiting confirmation.
        one_sentence_summary: One-sentence summary text (from summary.md if generated).

    Returns:
        Path to index.md.
    """
    env = _get_template_env()
    template = env.get_template("index.md.j2")

    authors = paper.get("authors", [])
    if isinstance(authors, str):
        import json
        try:
            authors = json.loads(authors)
        except (json.JSONDecodeError, TypeError):
            authors = [authors]

    content = template.render(
        title=paper.get("title", ""),
        authors=authors,
        year=year,
        venue=paper.get("venue", "") or "",
        doi=paper.get("doi", "") or "",
        language=paper.get("language", "unknown"),
        slug=slug,
        paper_id=paper.get("id", ""),
        parser=paper.get("parser", "docling"),
        parse_quality=paper.get("parse_quality", "medium"),
        fallback_used=paper.get("fallback_used", 0),
        tags=tags or [],
        has_translation=False,
        one_sentence_summary=one_sentence_summary or "",
        citing_papers=citing_papers or [],
        cited_by_papers=cited_by_papers or [],
        pending_refs=pending_refs or [],
    )

    paper_dir = vault / "papers" / str(year or "unknown") / slug
    paper_dir.mkdir(parents=True, exist_ok=True)
    index_path = paper_dir / "index.md"
    index_path.write_text(content, encoding="utf-8")
    return index_path


def write_summary_md(
    vault: Path,
    year: int | None,
    slug: str,
    title: str,
    summary_result,
) -> Path:
    """Write summary.md for a paper.

    Args:
        vault: Vault root path.
        year: Publication year.
        slug: Paper slug.
        title: Paper title.
        summary_result: SummaryResult Pydantic model.

    Returns:
        Path to summary.md.
    """
    env = _get_template_env()
    template = env.get_template("summary.md.j2")

    content = template.render(
        title=title,
        one_sentence_summary=summary_result.one_sentence_summary,
        research_question=summary_result.research_question,
        method=summary_result.method,
        conclusions=summary_result.conclusions,
        use_cases=summary_result.use_cases,
        limitations=summary_result.limitations,
        relation_to_prior_work=summary_result.relation_to_prior_work,
    )

    paper_dir = vault / "papers" / str(year or "unknown") / slug
    paper_dir.mkdir(parents=True, exist_ok=True)
    summary_path = paper_dir / "summary.md"
    summary_path.write_text(content, encoding="utf-8")
    return summary_path


def write_qa_md(
    vault: Path,
    year: int | None,
    slug: str,
    title: str,
    qa_result,
) -> Path:
    """Write qa.md for a paper.

    Args:
        vault: Vault root path.
        year: Publication year.
        slug: Paper slug.
        title: Paper title.
        qa_result: QAResult Pydantic model.

    Returns:
        Path to qa.md.
    """
    env = _get_template_env()
    template = env.get_template("qa.md.j2")

    content = template.render(
        title=title,
        questions=[{"question": q.question, "answer": q.answer} for q in qa_result.questions],
    )

    paper_dir = vault / "papers" / str(year or "unknown") / slug
    paper_dir.mkdir(parents=True, exist_ok=True)
    qa_path = paper_dir / "qa.md"
    qa_path.write_text(content, encoding="utf-8")
    return qa_path


def write_glossary_md(
    vault: Path,
    year: int | None,
    slug: str,
    title: str,
    glossary_result,
) -> Path:
    """Write glossary.md for a paper.

    Args:
        vault: Vault root path.
        year: Publication year.
        slug: Paper slug.
        title: Paper title.
        glossary_result: GlossaryResult Pydantic model.

    Returns:
        Path to glossary.md.
    """
    env = _get_template_env()
    template = env.get_template("glossary.md.j2")

    content = template.render(
        title=title,
        entries=[
            {
                "term_zh": e.term_zh,
                "term_en": e.term_en,
                "definition": e.definition,
                "section": e.section,
            }
            for e in glossary_result.entries
        ],
    )

    paper_dir = vault / "papers" / str(year or "unknown") / slug
    paper_dir.mkdir(parents=True, exist_ok=True)
    glossary_path = paper_dir / "glossary.md"
    glossary_path.write_text(content, encoding="utf-8")
    return glossary_path


def write_translate_md(
    vault: Path,
    year: int | None,
    slug: str,
    translated_text: str,
) -> Path:
    """Write translated.md for a paper.

    Args:
        vault: Vault root path.
        year: Publication year.
        slug: Paper slug.
        translated_text: Translated markdown text.

    Returns:
        Path to translated.md.
    """
    paper_dir = vault / "papers" / str(year or "unknown") / slug
    paper_dir.mkdir(parents=True, exist_ok=True)
    translate_path = paper_dir / "translated.md"
    translate_path.write_text(translated_text, encoding="utf-8")
    return translate_path


def write_papers_index(vault: Path, papers: List[dict]) -> Path:
    """Generate and write the master papers/index.md.

    Args:
        vault: Vault root path.
        papers: List of paper dicts.

    Returns:
        Path to papers/index.md.
    """
    env = _get_template_env()
    template = env.get_template("papers_index.md.j2")

    # Group papers by year
    by_year: Dict[str, List[dict]] = {}
    for p in papers:
        y = p.get("year") or "Unknown"
        by_year.setdefault(y, []).append(p)

    # Sort years descending (Unknown goes last)
    def year_sort_key(y):
        if y == "Unknown":
            return -1
        return y
    sorted_years = sorted(by_year.keys(), key=year_sort_key, reverse=True)
    grouped = [(y, sorted(by_year[y], key=lambda x: x.get("slug", ""))) for y in sorted_years]

    content = template.render(grouped_papers=grouped)

    papers_dir = vault / "papers"
    papers_dir.mkdir(parents=True, exist_ok=True)
    index_path = papers_dir / "index.md"
    index_path.write_text(content, encoding="utf-8")
    return index_path
