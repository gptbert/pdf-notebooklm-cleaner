from __future__ import annotations

import argparse
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import fitz  # PyMuPDF
import numpy as np
from PIL import Image

from . import __version__


@dataclass(frozen=True)
class CleanConfig:
    dpi: int = 200
    search_width_ratio: float = 0.16
    search_height_ratio: float = 0.12
    focus_left_ratio: float = 0.28
    focus_top_ratio: float = 0.24
    edge_margin_px: int = 16
    dark_threshold: int = 205
    bbox_pad_px: int = 14
    min_dark_pixels: int = 40
    fallback_box_ratio_w: float = 0.11
    fallback_box_ratio_h: float = 0.045
    fallback_inset_right_px: int = 16
    fallback_inset_bottom_px: int = 16
    png_compress_level: int = 3


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="pdf-notebooklm-cleaner",
        description=(
            "Render each PDF page to a full-page PNG, remove the NotebookLM mark in the "
            "bottom-right area, then export a ZIP of screenshots plus a cleaned PDF."
        ),
    )
    parser.add_argument("input_pdf", help="Input PDF path")
    parser.add_argument(
        "-o",
        "--output-dir",
        default=None,
        help="Output directory. Defaults to <input_stem>_cleaned beside the PDF.",
    )
    parser.add_argument("--dpi", type=int, default=200, help="Render DPI, default: 200")
    parser.add_argument(
        "--prefix",
        default="page",
        help="PNG filename prefix inside the screenshots folder, default: page",
    )
    parser.add_argument(
        "--search-width-ratio",
        type=float,
        default=0.16,
        help="Right-side search window width as fraction of page width, default: 0.16",
    )
    parser.add_argument(
        "--search-height-ratio",
        type=float,
        default=0.12,
        help="Bottom-side search window height as fraction of page height, default: 0.12",
    )
    parser.add_argument(
        "--dark-threshold",
        type=int,
        default=205,
        help="Pixel darkness threshold for auto box detection, default: 205",
    )
    parser.add_argument(
        "--bbox-pad-px",
        type=int,
        default=14,
        help="Padding added around the detected mark box, default: 14",
    )
    parser.add_argument(
        "--edge-margin-px",
        type=int,
        default=16,
        help=(
            "Keep this many pixels from the right/bottom edges untouched to preserve borders, "
            "default: 16"
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser.parse_args(argv)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def render_page(page: fitz.Page, dpi: int) -> Image.Image:
    zoom = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)


def estimate_background(arr: np.ndarray, box: tuple[int, int, int, int]) -> tuple[int, int, int]:
    x1, y1, x2, y2 = box
    h, w, _ = arr.shape
    samples: list[np.ndarray] = []
    pad = 8

    regions = [
        arr[max(0, y1 - pad):y1, max(0, x1 - pad):min(w, x2 + pad)],
        arr[y2:min(h, y2 + pad), max(0, x1 - pad):min(w, x2 + pad)],
        arr[max(0, y1 - pad):min(h, y2 + pad), max(0, x1 - pad):x1],
        arr[max(0, y1 - pad):min(h, y2 + pad), x2:min(w, x2 + pad)],
    ]
    for region in regions:
        if region.size:
            samples.append(region.reshape(-1, 3))

    if not samples:
        return (255, 255, 255)

    median_rgb = np.median(np.concatenate(samples, axis=0), axis=0)
    return tuple(int(v) for v in median_rgb)


def clamp_box(box: tuple[int, int, int, int], w: int, h: int) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = box
    x1 = max(0, min(w - 1, x1))
    y1 = max(0, min(h - 1, y1))
    x2 = max(x1 + 1, min(w, x2))
    y2 = max(y1 + 1, min(h, y2))
    return x1, y1, x2, y2


def detect_mark_box(img: Image.Image, cfg: CleanConfig) -> tuple[int, int, int, int]:
    gray = np.array(img.convert("L"))
    h, w = gray.shape

    sw = max(40, int(w * cfg.search_width_ratio))
    sh = max(30, int(h * cfg.search_height_ratio))
    sx1 = w - sw
    sy1 = h - sh
    crop = gray[sy1:h, sx1:w]

    fx1 = int(crop.shape[1] * cfg.focus_left_ratio)
    fy1 = int(crop.shape[0] * cfg.focus_top_ratio)
    fx2 = max(fx1 + 1, crop.shape[1] - cfg.edge_margin_px)
    fy2 = max(fy1 + 1, crop.shape[0] - cfg.edge_margin_px)
    focus = crop[fy1:fy2, fx1:fx2]

    ys, xs = np.where(focus < cfg.dark_threshold)
    if xs.size >= cfg.min_dark_pixels:
        x1 = sx1 + fx1 + int(xs.min()) - cfg.bbox_pad_px
        y1 = sy1 + fy1 + int(ys.min()) - cfg.bbox_pad_px
        x2 = sx1 + fx1 + int(xs.max()) + 1 + cfg.bbox_pad_px
        y2 = sy1 + fy1 + int(ys.max()) + 1 + cfg.bbox_pad_px
        return clamp_box((x1, y1, x2, y2), w, h)

    bw = max(80, int(w * cfg.fallback_box_ratio_w))
    bh = max(32, int(h * cfg.fallback_box_ratio_h))
    x2 = w - cfg.fallback_inset_right_px
    y2 = h - cfg.fallback_inset_bottom_px
    x1 = x2 - bw
    y1 = y2 - bh
    return clamp_box((x1, y1, x2, y2), w, h)


def clean_mark(img: Image.Image, cfg: CleanConfig) -> tuple[Image.Image, tuple[int, int, int, int]]:
    rgb = np.array(img.convert("RGB"))
    box = detect_mark_box(img, cfg)
    fill = estimate_background(rgb, box)
    x1, y1, x2, y2 = box
    rgb[y1:y2, x1:x2] = np.array(fill, dtype=np.uint8)
    return Image.fromarray(rgb, mode="RGB"), box


def write_zip(zip_path: Path, files: Iterable[Path], base_dir: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in files:
            zf.write(file_path, arcname=str(file_path.relative_to(base_dir)))


def build_pdf_from_images(images: Iterable[Path], pdf_path: Path) -> None:
    out = fitz.open()
    for image_path in images:
        with Image.open(image_path) as im:
            w, h = im.size
        page = out.new_page(width=w, height=h)
        page.insert_image(page.rect, filename=str(image_path))
    out.save(str(pdf_path), deflate=True)
    out.close()


def process_pdf(input_pdf: Path, output_dir: Path, prefix: str, cfg: CleanConfig) -> tuple[Path, Path]:
    screenshots_dir = output_dir / "screenshots"
    ensure_dir(screenshots_dir)

    cleaned_pdf = output_dir / f"{input_pdf.stem}_clean.pdf"
    screenshots_zip = output_dir / f"{input_pdf.stem}_screenshots.zip"

    doc = fitz.open(str(input_pdf))
    saved_images: list[Path] = []

    print(f"[1/3] Rendering and cleaning {doc.page_count} pages...")
    for i, page in enumerate(doc, start=1):
        img = render_page(page, cfg.dpi)
        cleaned, box = clean_mark(img, cfg)
        png_path = screenshots_dir / f"{prefix}_{i:02d}.png"
        cleaned.save(png_path, compress_level=cfg.png_compress_level)
        saved_images.append(png_path)
        print(f"  - page {i:02d}: cleaned box={box}")
    doc.close()

    print("[2/3] Building cleaned PDF...")
    build_pdf_from_images(saved_images, cleaned_pdf)

    print("[3/3] Writing screenshots ZIP...")
    write_zip(screenshots_zip, saved_images, output_dir)
    return cleaned_pdf, screenshots_zip


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    input_pdf = Path(args.input_pdf).expanduser().resolve()
    if not input_pdf.exists():
        print(f"Input PDF not found: {input_pdf}", file=sys.stderr)
        return 2
    if input_pdf.suffix.lower() != ".pdf":
        print(f"Input is not a PDF: {input_pdf}", file=sys.stderr)
        return 2

    cfg = CleanConfig(
        dpi=args.dpi,
        search_width_ratio=args.search_width_ratio,
        search_height_ratio=args.search_height_ratio,
        dark_threshold=args.dark_threshold,
        bbox_pad_px=args.bbox_pad_px,
        edge_margin_px=args.edge_margin_px,
    )

    output_dir = (
        Path(args.output_dir).expanduser().resolve()
        if args.output_dir
        else input_pdf.with_name(f"{input_pdf.stem}_cleaned")
    )
    ensure_dir(output_dir)

    cleaned_pdf, screenshots_zip = process_pdf(
        input_pdf=input_pdf,
        output_dir=output_dir,
        prefix=args.prefix,
        cfg=cfg,
    )
    print("Done.")
    print(f"Clean PDF: {cleaned_pdf}")
    print(f"Screenshots ZIP: {screenshots_zip}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
