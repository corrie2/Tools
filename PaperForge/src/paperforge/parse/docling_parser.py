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

        # Track warnings during parsing
        parse_warnings = []

        result = converter.convert(str(pdf_path))
        doc = result.document

        # Export to markdown
        markdown = doc.export_to_markdown()

        # Check for partial extraction indicators
        if not markdown.strip():
            parse_warnings.append("empty markdown output")
        elif len(markdown.strip()) < 200:
            parse_warnings.append(f"very short output ({len(markdown.strip())} chars)")

        # Extract figures
        figures: Dict[str, Path] = {}
        if save_figures and output_dir:
            fig_dir = output_dir / "figures"
            fig_dir.mkdir(parents=True, exist_ok=True)
            try:
                # Try Docling's picture extraction API (version-dependent)
                picture_items = None
                if hasattr(doc, 'pictures'):
                    picture_items = doc.pictures
                elif hasattr(doc, 'iterate_picture_items'):
                    picture_items = list(doc.iterate_picture_items())
                elif hasattr(doc, 'body'):
                    # Fallback: iterate body items and filter for pictures
                    from docling.datamodel.document import PictureItem
                    picture_items = [
                        item for item in doc.body
                        if isinstance(item, PictureItem)
                    ]

                if picture_items:
                    for i, item in enumerate(picture_items):
                        try:
                            # Handle both (element, image) tuples and PictureItem objects
                            if isinstance(item, tuple):
                                element, image = item
                            else:
                                element = item
                                image = getattr(item, 'image', None)

                            if image is not None:
                                fig_name = f"fig_{i + 1:03d}.png"
                                fig_path = fig_dir / fig_name
                                if hasattr(image, 'save'):
                                    image.save(str(fig_path))
                                elif hasattr(image, 'to_pil'):
                                    image.to_pil().save(str(fig_path))
                                figures[fig_name] = fig_path
                        except Exception as e:
                            parse_warnings.append(f"figure {i}: {e}")
                            logger.debug(f"Failed to extract picture {i}: {e}")
            except Exception as e:
                parse_warnings.append(f"figure extraction: {e}")
                logger.warning(f"Failed to extract figures: {e}")

        # Extract tables
        tables: List[str] = []
        if save_tables:
            try:
                for table in doc.tables:
                    tables.append(table.export_to_markdown())
            except Exception as e:
                parse_warnings.append(f"table extraction: {e}")
                logger.warning("Table extraction failed: %s", e)

        # Determine quality based on completeness
        if parse_warnings:
            # Had errors/warnings during parsing
            if markdown.strip() and len(markdown.strip()) > 500:
                quality = "medium"  # Got content but with issues
            else:
                quality = "low"     # Minimal content with errors
        else:
            quality = "high"        # Clean parse

        return ParseResult(
            markdown=markdown,
            figures=figures,
            tables=tables,
            parser="docling",
            quality=quality,
        )

    except Exception as e:
        logger.warning(f"Docling parsing failed: {e}")
        return None
