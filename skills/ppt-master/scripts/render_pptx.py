#!/usr/bin/env python3
"""Rasterize an already-rendered PPT PDF and build a compact contact sheet.

LibreOffice process ownership belongs to ``axion-agent-v2 ppt-process render``.
This helper deliberately accepts PDF only: it cannot choose a renderer, retry a
conversion, modify the source deck, inspect providers, or invoke an LLM.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pymupdf as fitz
from PIL import Image, ImageDraw, ImageOps, ImageStat


def configure_utf8_stdio() -> None:
    """Keep JSON and diagnostics stable under Windows console code pages."""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def render_pdf(pdf: Path, output_dir: Path) -> tuple[list[Path], list[int]]:
    """Render all PDF pages to PNG and flag visually near-empty slides."""

    slide_paths: list[Path] = []
    blank_suspects: list[int] = []
    with fitz.open(pdf) as document:
        if document.page_count == 0:
            raise RuntimeError("rendered PDF contains no pages")
        reference_size: tuple[int, int] | None = None
        for index, page in enumerate(document, start=1):
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            slide_path = output_dir / f"slide-{index:02d}.png"
            pixmap.save(slide_path)
            with Image.open(slide_path) as slide:
                size = slide.size
                if reference_size is None:
                    reference_size = size
                elif size != reference_size:
                    raise RuntimeError(
                        f"inconsistent rendered page size at slide {index}: "
                        f"{size} != {reference_size}"
                    )
                sample = slide.convert("RGB").resize((160, 90))
                if sum(ImageStat.Stat(sample).stddev) < 3.0:
                    blank_suspects.append(index)
            slide_paths.append(slide_path.resolve())
    return slide_paths, blank_suspects


def build_contact_sheet(slides: list[Path], output_dir: Path) -> Path:
    """Compose labeled slide thumbnails into one bounded JPEG."""

    columns = 2
    thumb_width = 800
    label_height = 38
    gap = 24
    with Image.open(slides[0]) as first:
        thumb_height = round(thumb_width * first.height / first.width)
    rows = (len(slides) + columns - 1) // columns
    width = columns * thumb_width + (columns + 1) * gap
    height = rows * (thumb_height + label_height) + (rows + 1) * gap
    sheet = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(sheet)
    for index, slide_path in enumerate(slides):
        row, column = divmod(index, columns)
        left = gap + column * (thumb_width + gap)
        top = gap + row * (thumb_height + label_height + gap)
        draw.text((left, top), f"Slide {index + 1:02d}", fill="#20242A")
        with Image.open(slide_path) as slide:
            thumbnail = ImageOps.contain(
                slide.convert("RGB"), (thumb_width, thumb_height)
            )
            sheet.paste(thumbnail, (left, top + label_height))
    path = output_dir / "contact-sheet.jpg"
    sheet.save(path, format="JPEG", quality=90, optimize=True)
    return path.resolve()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the intentionally PDF-only rasterization contract."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", required=True, help="LibreOffice-produced PDF")
    parser.add_argument("--output-dir", required=True, help="dedicated output directory")
    parser.add_argument("--json", action="store_true", help="emit one compact JSON receipt")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run per-page rasterization, contact-sheet creation, and receipt output."""

    configure_utf8_stdio()
    args = parse_args(argv)
    try:
        pdf = Path(args.pdf).expanduser().resolve(strict=True)
        if not pdf.is_file() or pdf.suffix.lower() != ".pdf":
            raise ValueError(f"input is not a PDF file: {pdf}")
        output_dir = Path(args.output_dir).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        slides, blank_suspects = render_pdf(pdf, output_dir)
        contact_sheet = build_contact_sheet(slides, output_dir)
        receipt = {
            "status": "passed",
            "slide_count": len(slides),
            "render_dir": str(output_dir),
            "pdf": str(pdf),
            "contact_sheet": str(contact_sheet),
            "slides": [str(path) for path in slides],
            "blank_suspects": blank_suspects,
        }
        print(
            json.dumps(
                receipt,
                ensure_ascii=False,
                separators=(",", ":") if args.json else None,
                indent=None if args.json else 2,
            )
        )
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI boundary returns concise failure.
        print(f"render_pptx: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
