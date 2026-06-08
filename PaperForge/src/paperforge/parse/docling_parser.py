"""Docling-based PDF parser — primary parser for PaperForge."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ParseResult:
    """Result of PDF parsing."""
    markdown: str = ""
    figures: Dict[str, Path] = field(default_factory=dict)
    tables: List[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    parser: str = "docling"
    quality: str = "high"


def parse_with_docling(
    pdf_path: Path,
    output_dir: Optional[Path] = None,
    save_figures: bool = True,
    save_tables: bool = True,
) -> Optional[ParseResult]:
    """Parse PDF using Docling.

    Args:
        pdf_path: Path to the PDF file.
        output_dir: Directory to save extracted figures.
        save_figures: Whether to extract and save figures.
        save_tables: Whether to extract tables.

    Returns:
        ParseResult on success, None on failure.
    """
    try:
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.datamodel.base_models import InputFormat
    except ImportError:
        logger.warning("Docling not installed, cannot use primary parser")
        return None

    try:
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = False
        pipeline_options.do_table_structure = save_tables

        converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
        )

        result = converter.convert(str(pdf_path))
        doc = result.document

        # Export to markdown
        markdown = doc.export_to_markdown()

        # Extract figures
        figures: Dict[str, Path] = {}
        if save_figures and output_dir:
            fig_dir = output_dir / "figures"
            fig_dir.mkdir(parents=True, exist_ok=True)
            try:
                for i, (element, image) in enumerate(doc.iterate_picture_items()):
                    fig_name = f"fig_{i + 1:03d}.png"
                    fig_path = fig_dir / fig_name
                    image.save(str(fig_path))
                    figures[fig_name] = fig_path
            except Exception as e:
                logger.warning(f"Failed to extract figures: {e}")

        # Extract tables
        tables: List[str] = []
        if save_tables:
            try:
                for table in doc.tables:
                    tables.append(table.export_to_markdown())
            except Exception:
                pass

        return ParseResult(
            markdown=markdown,
            figures=figures,
            tables=tables,
            parser="docling",
            quality="high" if markdown.strip() else "low",
        )

    except Exception as e:
        logger.warning(f"Docling parsing failed: {e}")
        return None
