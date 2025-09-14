# Nametag Generator

Generate printable nametags (default: 4 per landscape page) from a CSV of students. Supports auto-scaling names, smart two-line layout for long names, optional tent cards with fold lines, and an optional preferred name override CSV keyed by netid.

## Features
- Auto-detects a "Full name" column (accepts variations like "Full name", "Name", etc.)
- Optional preferred names via `netid` → `preferred_name` mapping
- Landscape pages with configurable grid (`--rows`, `--cols`)
- Tent cards with dashed fold lines (`--tent`, `--tent-style tri|bi`)
- Auto font sizing and two-line split for long names
- Thin cut border (disable with `--no-border`)
- A4 or Letter page sizes

## Requirements
- Python 3.8+
- Dependencies (install via pip):
  - `reportlab`

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

## Quick start
1. Ensure you have a CSV with a name column (e.g., `Full name`) and, optionally, an `Email` column if you plan to use preferred names.
2. Run the script on your CSV:

```bash
python generate_nametags.py data/5410-25/aug26-students.csv \
  --output nametags.pdf \
  --footer "INFO 5410, Urban Systems, Fall 2025"
```

This writes `nametags.pdf` (4 per page, Letter landscape) to the repo root.

## Prepare your data
### Students CSV
- Must include a name column. The script tries to detect the full name field by normalizing headers (e.g., `Full name`, `Name`, `Student name`). If it cannot find a name-like column, it will error.
- If you plan to use preferred names, include an `Email` column. The script derives `netid` from the part before `@`.
- CSV encoding should be UTF-8. UTF-8 with BOM is also accepted.

Example (headers simplified):

```csv
Full name,Email
Ada Lovelace,ada@university.edu
Grace Hopper,grace@university.edu
```

### Preferred names CSV (optional)
Provide a small CSV with headers `netid,preferred_name`. Empty `preferred_name` values are allowed (they will fall back to the full name).

```csv
netid,preferred_name
ada,Ada
grace,Admiral Hopper
```

When provided via `--preferred-names`, the script will:
- Parse `netid` from the `Email` field in the students CSV
- If a non-empty `preferred_name` exists for that `netid`, use it on the nametag; otherwise use the full name

## CLI usage
Basic syntax:

```bash
python generate_nametags.py path/to/students.csv \
  --output nametags.pdf \
  --footer "Course, Term" \
  [--page-size letter|a4] [--no-border] \
  [--rows N --cols M] \
  [--tent] [--tent-style tri|bi] \
  [--preferred-names path/to/preferred_names.csv]
```

Options:
- `input_csv` (positional): Path to the students CSV file.
- `-o, --output` (default: `nametags.pdf`): Output PDF path.
- `--footer` (default: `INFO 5410, Urban Systems, Fall 2025`): Footer text on each tag.
- `--page-size` (`letter`|`a4`, default `letter`): Page size (landscape orientation).
- `--no-border`: Disable the thin cut border around each tag.
- `--rows` (default `2`): Rows per page.
- `--cols` (default `2`): Columns per page.
- `--tent`: Generate tent cards instead of flat cards.
- `--tent-style` (`tri`|`bi`, default `tri`): Tent layout style.
  - `tri`: Three vertical panels per tag (back, front, flap). Back panel is rotated so it’s upright when folded. Dashed fold lines are drawn.
  - `bi`: Two panels per tag (nametag over flap) with a single dashed fold line.
- `--preferred-names`: Path to a CSV with headers `netid,preferred_name`.

Notes on defaults for tent cards:
- If you run with `--tent` and leave the default grid `--rows 2 --cols 2`, the script automatically adjusts the grid to fit 2 tent cards per page:
  - `--tent-style tri` ⇒ `1` row × `2` columns
  - `--tent-style bi` ⇒ `2` rows × `1` column
- If you explicitly set `--rows`/`--cols`, your values are respected.

## Examples
- Basic 4-per-page nametags (Letter):
```bash
python generate_nametags.py data/5410-25/aug26-students.csv \
  --output nametags.pdf \
  --footer "INFO 5410, Urban Systems, Fall 2025"
```

- With preferred names override:
```bash
python generate_nametags.py data/5410-25/sep2-students.csv \
  --preferred-names data/5410-25/sep2_preferred_names.csv \
  --output nametags.pdf
```

- A4 paper, no border:
```bash
python generate_nametags.py data/5410-25/sep2-students.csv \
  --page-size a4 --no-border
```

- 3×3 grid (9 per page):
```bash
python generate_nametags.py data/5410-25/sep2-students.csv \
  --rows 3 --cols 3
```

- Tent cards (tri-panel), 2 per page:
```bash
python generate_nametags.py data/5410-25/sep2-students.csv \
  --tent --tent-style tri --footer "INFO 5410"
```

- Tent cards (bi-panel), 2 per page:
```bash
python generate_nametags.py data/5410-25/sep2-students.csv \
  --tent --tent-style bi --footer "INFO 5410"
```

## Output details
- PDF is landscape and titled "Nametags".
- Font: `Helvetica-Bold` for names, `Helvetica` for footer.
- Names auto-scale to fit width and height, with a two-line split when helpful.
- Footer is centered near the bottom of each tag and may shrink slightly to fit.
- Borders are thin to act as cut guides; tent cards add dashed fold lines and a light "Fold/Glue Flap" label where applicable.

## Printing tips
- Print at 100% (no scaling) on the selected page size (Letter/A4).
- Use heavier paper or card stock for best results.
- If borders are enabled, cut just inside the line for clean edges.
- For tent cards, fold along the dashed lines; a glue stick or double-sided tape helps the flap hold.

## Troubleshooting
- "Could not find a 'Full Name' column in the CSV": Ensure your CSV has a name-like header. Try renaming the column to `Full name` if detection fails.
- Preferred names didn’t apply: Ensure the students CSV has an `Email` column and your preferred names CSV has the correct `netid` (the part before `@`). Empty `preferred_name` values intentionally fall back to the full name.
- "No names found in CSV.": Check for empty or malformed rows and verify the correct input file path.

## Project structure
- `generate_nametags.py`: CLI for generating nametags/tent cards
- `requirements.txt`: Python dependency pin(s)
- `data/` (examples): Sample student and preferred name CSVs
- `nametags.pdf`: Example output
