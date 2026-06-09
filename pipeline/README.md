# Wild Range — Data Pipeline

This folder contains the two-script pipeline for building `data/animals.js`
from real GBIF occurrence data.

---

## How it works

```
GBIF API
   ↓
fetch_animals.py       → review/animals_meta.csv
                       → review/animals_ranges.geojson
   ↓
You review & edit both files
   ↓
build_animals_js.py    → ../data/animals.js
```

---

## Setup

```bash
pip install requests shapely numpy pandas scipy
```

---

## Step 1 — Fetch from GBIF

```bash
python3 fetch_animals.py
```

This will:
- Resolve each species name against the GBIF taxonomy
- Download up to 2,000 occurrence records per species
- Build alpha-shape (concave hull) range polygons from the points
- Write two files to `review/`

Takes ~10–30 minutes for the full species list depending on your connection.

**GBIF attribution required** (CC BY 4.0) — keep the footer link in the game:
> Range data: GBIF.org

---

## Step 2 — Review & edit

### `review/animals_meta.csv`

Open in Excel or Google Sheets. Edit these columns:

| Column | What to do |
|--------|-----------|
| `name` | Correct common name if needed |
| `emoji` | Change if wrong |
| `hint` | Edit the in-game clue — keep it helpful but not a giveaway |
| `status` | **Verify against [iucnredlist.org](https://www.iucnredlist.org)** — GBIF doesn't have status reliably |
| `fact` | Add an interesting conservation fact (shown after guessing) |
| `region` | Short description of where the animal lives |
| `include` | Set to `no` to exclude a species from the game |

**Do not edit**: `id`, `scientific_name`, `alpha_used`, `point_count`, `polygon_count`

### `review/animals_ranges.geojson`

Inspect visually at **[geojson.io](https://geojson.io)** — paste the file contents.

Common issues to fix:
- **Too wide** (includes ocean or wrong continents) → increase `alpha_override` in `SPECIES_LIST` and re-fetch, or manually edit vertices
- **Too many holes** → decrease `alpha_override` (try 1.5 or 2.0)
- **Split into too many pieces** → decrease `alpha_override`
- **Offshore records polluting the range** → edit the GeoJSON to remove stray polygons

You can edit GeoJSON directly on geojson.io and save the result back to `review/animals_ranges.geojson`.

---

## Step 3 — Build

```bash
python3 build_animals_js.py
```

This reads your edited review files and generates `../data/animals.js`.
Run this any time you make changes to the review files.

---

## Adding more species

Edit `SPECIES_LIST` in `fetch_animals.py`. Each entry is:

```python
("Scientific name",  "Common Name",  "emoji",  "hint text",  "STATUS",  alpha)
```

- `alpha`: controls polygon tightness
  - Wide-ranging ocean/global species: `1.5`
  - Continent-scale ranges: `2.0–3.0`
  - Regional species: `3.0–5.0`
  - Tiny/island ranges: `6.0–8.0`

Re-run `fetch_animals.py` — it only fetches species not already in the GeoJSON,
so existing data is preserved.

---

## Updating conservation status

GBIF occurrence data does **not** include reliable IUCN status. Always verify
`status` manually in the CSV against:
- https://www.iucnredlist.org (authoritative)
- https://en.wikipedia.org/wiki/Special:Search (quick cross-check)

Valid values: `CR`, `EN`, `VU`, `NT`, `LC`, `DD`

---

## File reference

```
pipeline/
├── fetch_animals.py         ← edit SPECIES_LIST here to add animals
├── build_animals_js.py      ← converts review files → animals.js
├── README.md                ← this file
└── review/
    ├── animals_meta.csv     ← YOU EDIT THIS
    └── animals_ranges.geojson ← YOU EDIT/INSPECT THIS
```
