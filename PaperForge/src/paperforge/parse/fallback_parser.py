"""Fallback PDF parser using PyMuPDF + pdfplumber."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def parse_with_fallback(
    pdf_path: Path,
    output_dir: Optional[Path] = None,
    save_figures: bool = True,
    save_tables: bool = True,
) -> Optional["ParseResult"]:
    """Parse PDF using PyMuPDF for text/images and pdfplumber for tables.

    Args:
        pdf_path: Path to the PDF file.
        output_dir: Directory to save extracted figures.
        save_figures: Whether to extract and save figures.
        save_tables: Whether to extract tables.

    Returns:
        ParseResult on success, None on failure.
    """
    from paperforge.parse.docling_parser import ParseResult

    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.error("PyMuPDF not installed")
        return None

    try:
        doc = fitz.open(str(pdf_path))

        # Extract text as markdown (page by page)
        markdown_parts = []
        for i, page in enumerate(doc):
            text = page.get_text()
            if text.strip():
                markdown_parts.append(f"## Page {i + 1}\n\n{text.strip()}")
        markdown = "\n\n".join(markdown_parts)

        # Extract figures (embedded images)
        figures: Dict[str, Path] = {}
        if save_figures and output_dir:
            fig_dir = output_dir / "figures"
            fig_dir.mkdir(parents=True, exist_ok=True)
            fig_count = 0
            for page_idx, page in enumerate(doc):
                image_list = page.get_images(full=True)
                for img_idx, img_info in enumerate(image_list):
                    xref = img_info[0]
                    try:
                        base_image = doc.extract_image(xref)
                        if base_image:
                            fig_count += 1
                            fig_name = f"fig_{fig_count:03d}.png"
                            fig_path = fig_dir / fig_name
                            fig_path.write_bytes(base_image["image"])
                            figures[fig_name] = fig_path
                    except Exception as e:
                        logger.warning(f"Failed to extract image xref={xref}: {e}")

        # Extract tables using pdfplumber
        tables: List[str] = []
        if save_tables:
            try:
                import pdfplumber
                with pdfplumber.open(str(pdf_path)) as pdf:
                    for page in pdf.pages:
                        page_tables = page.extract_tables()
                        for table in page_tables:
                            if table:
                                # Convert to markdown table
                                md_table = _table_to_markdown(table)
                                if md_table:
                                    tables.append(md_table)
            except ImportError:
                logger.warning("pdfplumber not installed, skipping table extraction")
            except Exception as e:
                logger.warning(f"pdfplumber table extraction failed: {e}")

        doc.close()

        return ParseResult(
            markdown=markdown,
            figures=figures,
            tables=tables,
            parser="fallback",
            quality="medium" if markdown.strip() else "low",
        )

    except Exception as e:
        logger.warning(f"Fallback parsing failed: {e}")
        return None


def _table_to_markdown(table: list) -> str:
    """Convert a pdfplumber table (list of lists) to markdown format."""
    if not table or not table[0]:
        return ""
    # Clean cells
    cleaned = []
    for row in table:
        cleaned.append([str(cell).replace("\n", " ").strip() if cell else "" for cell in row])
    if not cleaned:
        return ""

    # Header row
    header = "| " + " | ".join(cleaned[0]) + " |"
    separator = "| " + " | ".join(["---"] * len(cleaned[0])) + " |"
    body_rows = []
    for row in cleaned[1:]:
        # Pad row to match header length
        while len(row) < len(cleaned[0]):
            row.append("")
        body_rows.append("| " + " | ".join(row[:len(cleaned[0])]) + " |")

    return "\n".join([header, separator] + body_rows)
