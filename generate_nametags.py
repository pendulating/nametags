#!/usr/bin/env python3
"""
Generate printable nametags (4 per landscape page) from a CSV.

Input CSV is expected to include a column for Full Name (e.g., "Full name").

Usage:
  python generate_nametags.py path/to/students.csv \
      --output nametags.pdf \
      --footer "INFO 5410, Urban Systems, Fall 2025" \
      [--page-size letter|a4] [--no-border] [--rows N --cols M] [--tent] [--tent-style tri|bi]

Dependencies: reportlab
"""

from __future__ import annotations

import argparse
import csv
import os
import re
from typing import Iterable, List, Optional, Sequence, Tuple, Dict

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, letter, landscape
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas


def normalize_header(header: str) -> str:
    """Normalize a CSV header to allow forgiving matches (e.g., "Full name" → "fullname")."""
    return re.sub(r"[^a-z0-9]", "", header.strip().lower())


def detect_fullname_field(fieldnames: Sequence[str]) -> Optional[str]:
    """Return the original header name that represents the full name column.

    We match by normalized header against common variants like fullname, name, studentname.
    """
    if not fieldnames:
        return None

    normalized_to_original = {normalize_header(h): h for h in fieldnames}
    candidate_keys = [
        "fullname",
        "name",
        "studentname",
        "student",
    ]
    for key in candidate_keys:
        if key in normalized_to_original:
            return normalized_to_original[key]
    # Fallback: look for header that contains "name" when normalized
    for norm, original in normalized_to_original.items():
        if "name" in norm:
            return original
    return None


def read_full_names_from_csv(
    csv_path: str,
    preferred_by_netid: Optional[Dict[str, str]] = None,
) -> List[str]:
    """Read the students CSV and return a list of display names.

    If a preferred names mapping is provided, attempt to derive a netid from the
    Email field (by splitting at '@') and, when a non-empty preferred_name exists
    for that netid, use it as the nametag text. Otherwise, fall back to the full name.
    """
    names: List[str] = []
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        full_name_field = detect_fullname_field(fieldnames)
        if not full_name_field:
            raise ValueError(
                "Could not find a 'Full Name' column in the CSV. "
                "Make sure there is a column like 'Full name'."
            )

        # Detect an Email-like field by normalized header containing 'email'
        email_field: Optional[str] = None
        normalized_to_original = {normalize_header(h): h for h in fieldnames}
        for norm, original in normalized_to_original.items():
            if "email" in norm:
                email_field = original
                break

        for row in reader:
            raw_full = row.get(full_name_field, "").strip()
            if not raw_full:
                continue
            clean_full = re.sub(r"\s+", " ", raw_full).strip().strip('"')
            if not clean_full:
                continue

            # Default to full name; override with preferred when available
            display_name = clean_full
            if preferred_by_netid and email_field:
                email_value = (row.get(email_field) or "").strip()
                if email_value and "@" in email_value:
                    netid = email_value.split("@", 1)[0].strip()
                    preferred = preferred_by_netid.get(netid)
                    if preferred is not None:
                        preferred_clean = preferred.strip()
                        if preferred_clean:
                            display_name = preferred_clean

            names.append(display_name)
    return names

def load_preferred_names_csv(csv_path: str) -> Dict[str, str]:
    """Load a mapping of netid -> preferred_name from a CSV.

    The CSV is expected to have headers: 'netid' and 'preferred_name'. Rows with
    missing netid are skipped. Preferred names may be empty strings; those are
    still loaded so we can detect "explicitly empty" versus "missing" if needed.
    """
    mapping: Dict[str, str] = {}
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            netid = (row.get("netid") or "").strip()
            if not netid:
                continue
            preferred_name = (row.get("preferred_name") or "").strip()
            mapping[netid] = preferred_name
    return mapping


def measure_text_width(pdf: canvas.Canvas, text: str, font_name: str, font_size: float) -> float:
    return pdf.stringWidth(text, font_name, font_size)


def find_font_size_for_line(
    pdf: canvas.Canvas,
    text: str,
    font_name: str,
    max_width: float,
    max_size: int = 72,
    min_size: int = 18,
) -> int:
    """Find the largest font size that allows the line to fit within max_width."""
    for size in range(max_size, min_size - 1, -1):
        if measure_text_width(pdf, text, font_name, size) <= max_width:
            return size
    return min_size


def try_two_line_split(
    pdf: canvas.Canvas,
    text: str,
    font_name: str,
    target_size: int,
    max_width: float,
) -> Optional[Tuple[List[str], int]]:
    """Try splitting text into two lines that both fit within max_width at target_size.

    Returns (lines, size) if successful, otherwise None.
    """
    words = text.split()
    if len(words) <= 1:
        return None
    best_split: Optional[Tuple[List[str], int]] = None
    # Try splits at each possible break; choose the one with the smallest max line width
    best_max_line_width = float("inf")
    for i in range(1, len(words)):
        line1 = " ".join(words[:i])
        line2 = " ".join(words[i:])
        w1 = measure_text_width(pdf, line1, font_name, target_size)
        w2 = measure_text_width(pdf, line2, font_name, target_size)
        maxw = max(w1, w2)
        if w1 <= max_width and w2 <= max_width and maxw < best_max_line_width:
            best_max_line_width = maxw
            best_split = ([line1, line2], target_size)
    return best_split


def layout_name_lines(
    pdf: canvas.Canvas,
    name_text: str,
    font_name: str,
    max_width: float,
    max_size: int = 72,
    min_size: int = 18,
) -> Tuple[List[str], int]:
    """Compute one- or two-line layout for the name that fits within max_width.

    Preference order:
      1) Single line at the largest possible size
      2) Two lines at the largest possible size where both lines fit
    """
    # First try single-line fit from large to small
    single_line_size = find_font_size_for_line(
        pdf, name_text, font_name, max_width, max_size=max_size, min_size=min_size
    )
    if measure_text_width(pdf, name_text, font_name, single_line_size) <= max_width:
        return [name_text], single_line_size

    # Try two-line splits starting from large to small
    for candidate_size in range(max_size, min_size - 1, -1):
        split = try_two_line_split(pdf, name_text, font_name, candidate_size, max_width)
        if split is not None:
            return split

    # Fallback to single line at min size
    return [name_text], min_size


def draw_nametag(
    pdf: canvas.Canvas,
    x: float,
    y: float,
    tag_width: float,
    tag_height: float,
    name_text: str,
    footer_text: str,
    draw_border: bool = True,
) -> None:
    padding_x = 0.35 * inch
    # Footer closer to bottom to free space for larger names
    padding_y = 0.12 * inch
    available_width = max(0.0, tag_width - 2 * padding_x)

    # Optional border to guide cutting
    if draw_border:
        pdf.setStrokeColor(colors.black)
        pdf.setLineWidth(0.8)
        pdf.rect(x, y, tag_width, tag_height, stroke=1, fill=0)

    # Footer
    footer_font = "Helvetica"
    footer_size = 10
    pdf.setFont(footer_font, footer_size)
    footer_y = y + padding_y
    footer_width = measure_text_width(pdf, footer_text, footer_font, footer_size)
    if footer_width > available_width:
        # Shrink footer if needed
        footer_size = find_font_size_for_line(pdf, footer_text, footer_font, available_width, max_size=14, min_size=8)
        pdf.setFont(footer_font, footer_size)
        footer_width = measure_text_width(pdf, footer_text, footer_font, footer_size)
    footer_x = x + (tag_width - footer_width) / 2.0
    pdf.setFillColor(colors.black)
    pdf.drawString(footer_x, footer_y, footer_text)

    # Name (centered in remaining space above footer)
    name_font = "Helvetica-Bold"
    name_area_top = y + tag_height - padding_y
    # Moderate gap above the footer to avoid intersection
    name_area_bottom = footer_y + footer_size + (0.20 * inch)
    name_area_height = max(0.0, name_area_top - name_area_bottom)

    # Allow larger names; vertical autoscale prevents overlap
    lines, font_size = layout_name_lines(
        pdf, name_text, name_font, available_width, max_size=96, min_size=18
    )
    pdf.setFont(name_font, font_size)

    line_gap_ratio = 0.15
    total_text_height = len(lines) * font_size + (len(lines) - 1) * (line_gap_ratio * font_size)
    if name_area_height > 0 and total_text_height > name_area_height:
        scale = name_area_height / total_text_height
        adjusted_size = max(int(font_size * scale), 14)
        font_size = adjusted_size
        pdf.setFont(name_font, font_size)
        total_text_height = len(lines) * font_size + (len(lines) - 1) * (line_gap_ratio * font_size)

    # Center within the available name area, but never below the footer gap
    min_gap_pts = 4
    start_y = max(
        name_area_bottom + min_gap_pts,
        name_area_bottom + (name_area_height - total_text_height) / 2.0,
    )
    for i, line in enumerate(lines):
        line_width = measure_text_width(pdf, line, name_font, font_size)
        text_x = x + (tag_width - line_width) / 2.0
        text_y = start_y + (len(lines) - 1 - i) * (font_size + line_gap_ratio * font_size)
        pdf.drawString(text_x, text_y, line)


def _draw_panel_content_at_origin(
    pdf: canvas.Canvas,
    region_width: float,
    region_height: float,
    name_text: str,
    footer_text: str,
    padding_x: float,
    padding_y: float,
) -> None:
    """Draws name and footer inside a region where the origin is at (0, 0)."""
    available_width = max(0.0, region_width - 2 * padding_x)

    # Footer
    footer_font = "Helvetica"
    footer_size = 10
    pdf.setFont(footer_font, footer_size)
    footer_y = padding_y
    footer_width = measure_text_width(pdf, footer_text, footer_font, footer_size)
    if footer_width > available_width:
        footer_size = find_font_size_for_line(pdf, footer_text, footer_font, available_width, max_size=14, min_size=8)
        pdf.setFont(footer_font, footer_size)
        footer_width = measure_text_width(pdf, footer_text, footer_font, footer_size)
    footer_x = (region_width - footer_width) / 2.0
    pdf.setFillColor(colors.black)
    pdf.drawString(footer_x, footer_y, footer_text)

    # Name block above footer area
    name_font = "Helvetica-Bold"
    name_area_top = region_height - padding_y
    name_area_bottom = footer_y + footer_size + (0.20 * inch)
    name_area_height = max(0.0, name_area_top - name_area_bottom)

    lines, font_size = layout_name_lines(
        pdf, name_text, name_font, available_width, max_size=84, min_size=18
    )
    pdf.setFont(name_font, font_size)
    line_gap_ratio = 0.15
    total_text_height = len(lines) * font_size + (len(lines) - 1) * (line_gap_ratio * font_size)
    if name_area_height > 0 and total_text_height > name_area_height:
        scale = name_area_height / total_text_height
        adjusted_size = max(int(font_size * scale), 14)
        font_size = adjusted_size
        pdf.setFont(name_font, font_size)
        total_text_height = len(lines) * font_size + (len(lines) - 1) * (line_gap_ratio * font_size)
    min_gap_pts = 4
    start_y = max(
        name_area_bottom + min_gap_pts,
        name_area_bottom + (name_area_height - total_text_height) / 2.0,
    )
    for i, line in enumerate(lines):
        line_width = measure_text_width(pdf, line, name_font, font_size)
        text_x = (region_width - line_width) / 2.0
        text_y = start_y + (len(lines) - 1 - i) * (font_size + line_gap_ratio * font_size)
        pdf.drawString(text_x, text_y, line)


def draw_tent_card(
    pdf: canvas.Canvas,
    x: float,
    y: float,
    tag_width: float,
    tag_height: float,
    name_text: str,
    footer_text: str,
    draw_border: bool = True,
) -> None:
    """Draw a tent-style nametag with three equal-height panels (back, front, flap).

    Layout per column (y increases upward):
      - Top third: back face (rotated 180° so it's upright when folded)
      - Middle third: front face (upright)
      - Bottom third: flap (blank, with light label)
    """
    panel_h = tag_height / 3.0
    pad_x = 0.35 * inch
    pad_y = 0.18 * inch

    # Outer cut border
    if draw_border:
        pdf.setStrokeColor(colors.black)
        pdf.setLineWidth(0.8)
        pdf.rect(x, y, tag_width, tag_height, stroke=1, fill=0)

    # Fold lines (dashed) between panels
    pdf.setStrokeColor(colors.black)
    pdf.setLineWidth(0.6)
    pdf.setDash(3, 3)
    pdf.line(x, y + panel_h, x + tag_width, y + panel_h)
    pdf.line(x, y + 2 * panel_h, x + tag_width, y + 2 * panel_h)
    pdf.setDash()  # reset

    # Middle panel (front face) content at origin translated to middle panel bottom-left
    pdf.saveState()
    pdf.translate(x, y + panel_h)
    _draw_panel_content_at_origin(pdf, tag_width, panel_h, name_text, footer_text, pad_x, pad_y)
    pdf.restoreState()

    # Top panel (back face) rotated 180° around its panel center
    pdf.saveState()
    top_origin_x = x
    top_origin_y = y + 2 * panel_h
    # Translate to top panel top-right corner then rotate 180 so origin becomes panel bottom-left
    pdf.translate(top_origin_x + tag_width, top_origin_y + panel_h)
    pdf.rotate(180)
    _draw_panel_content_at_origin(pdf, tag_width, panel_h, name_text, footer_text, pad_x, pad_y)
    pdf.restoreState()

    # Bottom panel label (flap)
    pdf.saveState()
    pdf.translate(x, y)
    pdf.setFont("Helvetica", 9)
    pdf.setFillColor(colors.grey)
    label = "Fold/Glue Flap"
    lw = measure_text_width(pdf, label, "Helvetica", 9)
    pdf.drawString((tag_width - lw) / 2.0, panel_h / 2.0 - 4, label)
    pdf.restoreState()


def draw_tent_card_bi(
    pdf: canvas.Canvas,
    x: float,
    y: float,
    tag_width: float,
    tag_height: float,
    name_text: str,
    footer_text: str,
    draw_border: bool = True,
) -> None:
    """Draw a two-panel tent: top half is nametag, bottom half is flap (equal height).

    Layout (y increases upward):
      - Top half: nametag content (upright)
      - Bottom half: flap area with label (for fold/glue)
    """
    half_h = tag_height / 2.0
    pad_x = 0.35 * inch
    pad_y = 0.18 * inch

    # Outer border
    if draw_border:
        pdf.setStrokeColor(colors.black)
        pdf.setLineWidth(0.8)
        pdf.rect(x, y, tag_width, tag_height, stroke=1, fill=0)

    # Fold line (dashed)
    pdf.setStrokeColor(colors.black)
    pdf.setLineWidth(0.6)
    pdf.setDash(3, 3)
    pdf.line(x, y + half_h, x + tag_width, y + half_h)
    pdf.setDash()

    # Top half: nametag
    pdf.saveState()
    pdf.translate(x, y + half_h)
    _draw_panel_content_at_origin(pdf, tag_width, half_h, name_text, footer_text, pad_x, pad_y)
    pdf.restoreState()

    # Bottom half: flap label
    pdf.saveState()
    pdf.translate(x, y)
    pdf.setFont("Helvetica", 10)
    pdf.setFillColor(colors.grey)
    label = "Fold/Glue Flap"
    lw = measure_text_width(pdf, label, "Helvetica", 10)
    pdf.drawString((tag_width - lw) / 2.0, half_h / 2.0 - 5, label)
    pdf.restoreState()


def generate_pdf(
    names: Sequence[str],
    output_path: str,
    footer_text: str,
    page_size_name: str = "letter",
    draw_border: bool = True,
    rows: int = 2,
    cols: int = 2,
    tent: bool = False,
    tent_style: str = "tri",
) -> None:
    # Page setup
    if page_size_name.lower() == "a4":
        base_size = A4
    else:
        base_size = letter
    page_width, page_height = landscape(base_size)

    pdf = canvas.Canvas(output_path, pagesize=(page_width, page_height))
    pdf.setTitle("Nametags")
    pdf.setAuthor("Nametag Generator")

    # Grid setup
    tags_per_row = max(1, int(cols))
    tags_per_col = max(1, int(rows))
    tags_per_page = tags_per_row * tags_per_col
    tag_width = page_width / tags_per_row
    tag_height = page_height / tags_per_col

    for idx, name in enumerate(names):
        if idx > 0 and idx % tags_per_page == 0:
            pdf.showPage()

        pos_in_page = idx % tags_per_page
        col_index = pos_in_page % tags_per_row
        row_index_top_down = pos_in_page // tags_per_row  # 0 for top row, 1 for bottom row

        # Convert top-down row index to reportlab's bottom-left origin
        # Top row y should be page_height - tag_height
        x = col_index * tag_width
        y = page_height - (row_index_top_down + 1) * tag_height

        if tent and tent_style == "tri":
            draw_tent_card(
                pdf,
                x,
                y,
                tag_width,
                tag_height,
                name_text=name,
                footer_text=footer_text,
                draw_border=draw_border,
            )
        elif tent and tent_style == "bi":
            draw_tent_card_bi(
                pdf,
                x,
                y,
                tag_width,
                tag_height,
                name_text=name,
                footer_text=footer_text,
                draw_border=draw_border,
            )
        else:
            draw_nametag(
                pdf,
                x,
                y,
                tag_width,
                tag_height,
                name_text=name,
                footer_text=footer_text,
                draw_border=draw_border,
            )

    pdf.save()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate 4-per-page landscape nametags from CSV.")
    parser.add_argument("input_csv", help="Path to the students CSV file")
    parser.add_argument(
        "-o",
        "--output",
        default="nametags.pdf",
        help="Output PDF path (default: nametags.pdf)",
    )
    parser.add_argument(
        "--footer",
        default="INFO 5410, Urban Systems, Fall 2025",
        help="Footer text to print on each nametag",
    )
    parser.add_argument(
        "--page-size",
        choices=["letter", "a4"],
        default="letter",
        help="Page size (landscape) to use (default: letter)",
    )
    parser.add_argument(
        "--no-border",
        action="store_true",
        help="Disable thin border around each nametag",
    )
    parser.add_argument(
        "--tent",
        action="store_true",
        help="Generate tent cards (2 per landscape page by default, with equal-height flap)",
    )
    parser.add_argument(
        "--tent-style",
        choices=["tri", "bi"],
        default="tri",
        help="Tent style: 'tri' (back/front/flap vertical) or 'bi' (nametag over flap)",
    )
    parser.add_argument(
        "--rows",
        type=int,
        default=2,
        help="Number of rows per page (default: 2)",
    )
    parser.add_argument(
        "--cols",
        type=int,
        default=2,
        help="Number of columns per page (default: 2)",
    )
    parser.add_argument(
        "--preferred-names",
        dest="preferred_names_csv",
        default=None,
        help="Path to a CSV with columns 'netid,preferred_name' to override names",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    preferred_map: Optional[Dict[str, str]] = None
    if args.preferred_names_csv:
        if not os.path.exists(args.preferred_names_csv):
            raise SystemExit(f"Preferred names CSV not found: {args.preferred_names_csv}")
        preferred_map = load_preferred_names_csv(args.preferred_names_csv)

    names = read_full_names_from_csv(args.input_csv, preferred_by_netid=preferred_map)
    if not names:
        raise SystemExit("No names found in CSV.")

    output_path = args.output
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # Defaults for tent cards:
    #  - tri: 2 per landscape page (1 row x 2 cols)
    #  - bi:  2 per landscape page (2 rows x 1 col)
    rows = args.rows
    cols = args.cols
    if args.tent and args.rows == 2 and args.cols == 2:
        if args.tent_style == "tri":
            rows, cols = 1, 2
        else:
            rows, cols = 2, 1

    generate_pdf(
        names=names,
        output_path=output_path,
        footer_text=args.footer,
        page_size_name=args.page_size,
        draw_border=(not args.no_border),
        rows=rows,
        cols=cols,
        tent=args.tent,
        tent_style=args.tent_style,
    )
    print(f"Wrote {len(names)} nametags to {output_path}")


if __name__ == "__main__":
    main()


