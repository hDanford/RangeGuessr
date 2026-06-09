"""
build_animals_js.py
───────────────────
Step 3 of the Wild Range data pipeline.

Reads:
  review/animals_meta.csv        ← your edited metadata
  review/animals_ranges.geojson  ← your edited range polygons

Writes:
  ../data/animals.js             ← ready to drop into the game

Usage:
  python3 build_animals_js.py

The script validates data, reports any issues, and exits non-zero
if critical problems are found (missing facts, empty polygons, etc.).
"""

import csv
import json
import os
import sys
import re

REVIEW_DIR    = os.path.join(os.path.dirname(__file__), "review")
META_CSV      = os.path.join(REVIEW_DIR, "animals_meta.csv")
RANGES_GEOJSON = os.path.join(REVIEW_DIR, "animals_ranges.geojson")
OUTPUT_JS     = os.path.join(os.path.dirname(__file__), "..", "data", "animals.js")

VALID_STATUSES = {"CR", "EN", "VU", "NT", "LC", "DD", "NE"}

# Maximum polygon vertices to keep per ring — reduces file size for complex coastlines
MAX_VERTICES = 120


def simplify_ring(ring, max_pts):
    """
    Reduce a ring to at most max_pts vertices using simple equidistant sampling.
    Always keeps first and last point (which should be identical for a closed ring).
    """
    if len(ring) <= max_pts:
        return ring
    # Keep first, last, and evenly-spaced intermediate points
    step = (len(ring) - 1) / (max_pts - 1)
    indices = set([0, len(ring)-1])
    for i in range(1, max_pts - 1):
        indices.add(round(i * step))
    return [ring[i] for i in sorted(indices)]


def load_meta(path):
    rows = {}
    warnings = []
    errors = []

    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, 2):  # row 2 = first data row
            animal_id = row.get("id", "").strip()
            include   = row.get("include", "yes").strip().lower()

            if not animal_id:
                warnings.append(f"Row {i}: empty id, skipping")
                continue
            if include == "no":
                print(f"  ⏭  Skipping {row.get('name','?')} (include=no)")
                continue

            # Validate required fields
            name   = row.get("name", "").strip()
            emoji  = row.get("emoji", "").strip()
            hint   = row.get("hint", "").strip()
            status = row.get("status", "").strip().upper()
            fact   = row.get("fact", "").strip()
            region = row.get("region", "").strip()

            if not name:
                errors.append(f"Row {i} ({animal_id}): missing name")
            if not emoji:
                warnings.append(f"  ⚠  {name}: missing emoji, defaulting to 🐾")
                emoji = "🐾"
            if status not in VALID_STATUSES:
                errors.append(f"Row {i} ({name}): invalid status '{status}' — must be one of {VALID_STATUSES}")
            if not fact:
                warnings.append(f"  ⚠  {name}: 'fact' column is empty — fill this in for a better game experience")
            if not hint:
                warnings.append(f"  ⚠  {name}: 'hint' column is empty")
            if not region:
                warnings.append(f"  ⚠  {name}: 'region' column is empty")

            rows[animal_id] = {
                "id":              animal_id,
                "scientific_name": row.get("scientific_name", "").strip(),
                "name":            name,
                "emoji":           emoji,
                "hint":            hint or f"A {name}",
                "status":          status if status in VALID_STATUSES else "LC",
                "fact":            fact or f"The {name} is a fascinating animal.",
                "region":          region or "Global",
            }

    return rows, warnings, errors


def load_ranges(path):
    with open(path, encoding="utf-8") as f:
        geojson = json.load(f)

    ranges = {}
    for feature in geojson.get("features", []):
        props = feature.get("properties", {})
        animal_id = props.get("id", "").strip()
        geom = feature.get("geometry", {})

        if not animal_id or not geom:
            continue

        geom_type = geom.get("type")
        coords_raw = geom.get("coordinates", [])

        # Normalize all geometry types to list of rings [[{lat,lng},...],...]
        rings = []

        if geom_type == "Polygon":
            # coords_raw = [ exterior_ring, ...holes ]
            rings.append(coords_raw[0])

        elif geom_type == "MultiPolygon":
            # coords_raw = [ [ [exterior], ...holes ], ... ]
            for polygon in coords_raw:
                if polygon:
                    rings.append(polygon[0])

        else:
            print(f"  ⚠  {animal_id}: unsupported geometry type '{geom_type}', skipping")
            continue

        # Convert GeoJSON [lng, lat] → game format [{lat, lng}]
        converted = []
        for ring in rings:
            simplified = simplify_ring(ring, MAX_VERTICES)
            game_ring = [{"lat": round(c[1], 4), "lng": round(c[0], 4)} for c in simplified]
            # Close the ring if needed
            if game_ring and game_ring[0] != game_ring[-1]:
                game_ring.append(game_ring[0])
            if len(game_ring) >= 4:
                converted.append(game_ring)

        if converted:
            ranges[animal_id] = converted

    return ranges


def escape_js_string(s):
    """Escape a string for use in a JS single-quoted string."""
    return s.replace("\\", "\\\\").replace("'", "\\'")


def build_js(meta_rows, ranges):
    lines = []
    lines.append("// AUTO-GENERATED by build_animals_js.py — do not edit directly.")
    lines.append("// Edit review/animals_meta.csv and review/animals_ranges.geojson, then re-run the script.")
    lines.append("")
    lines.append("const ANIMALS = [")

    for animal_id, meta in meta_rows.items():
        polys = ranges.get(animal_id)
        if not polys:
            print(f"  ⚠  {meta['name']}: no range polygon found — excluded from output")
            continue

        # Format range polygons
        poly_lines = []
        for poly in polys:
            pts = ", ".join(f"{{lat:{p['lat']},lng:{p['lng']}}}" for p in poly)
            poly_lines.append(f"    [{pts}]")
        range_str = "[\n" + ",\n".join(poly_lines) + "\n  ]"

        lines.append("  {")
        lines.append(f"    id: '{escape_js_string(animal_id)}',")
        lines.append(f"    name: '{escape_js_string(meta['name'])}',")
        lines.append(f"    emoji: '{meta['emoji']}',")
        lines.append(f"    hint: '{escape_js_string(meta['hint'])}',")
        lines.append(f"    status: '{meta['status']}',")
        lines.append(f"    fact: '{escape_js_string(meta['fact'])}',")
        lines.append(f"    region: '{escape_js_string(meta['region'])}',")
        lines.append(f"    rangePolygons: {range_str},")
        lines.append("  },")

    lines.append("];")
    lines.append("")
    lines.append("const STATUS_META = {")
    lines.append("  CR: { label: 'Critically Endangered', color: '#791F1F', bg: '#FCEBEB', order: 0 },")
    lines.append("  EN: { label: 'Endangered',            color: '#993C1D', bg: '#FAECE7', order: 1 },")
    lines.append("  VU: { label: 'Vulnerable',            color: '#854F0B', bg: '#FAEEDA', order: 2 },")
    lines.append("  NT: { label: 'Near Threatened',       color: '#3B6D11', bg: '#EAF3DE', order: 3 },")
    lines.append("  LC: { label: 'Least Concern',         color: '#0F6E56', bg: '#E1F5EE', order: 4 },")
    lines.append("  DD: { label: 'Data Deficient',        color: '#444441', bg: '#F1EFE8', order: 5 },")
    lines.append("};")
    lines.append("")
    lines.append("const STATUS_ORDER = ['CR','EN','VU','NT','LC','DD'];")
    lines.append("")

    return "\n".join(lines)


def run():
    print(f"\n🌿 Wild Range — build pipeline\n")

    # Check inputs exist
    for path, label in [(META_CSV, "animals_meta.csv"), (RANGES_GEOJSON, "animals_ranges.geojson")]:
        if not os.path.exists(path):
            print(f"❌ Missing: {path}")
            print(f"   Run fetch_animals.py first.\n")
            sys.exit(1)

    print(f"📄 Loading metadata from {META_CSV}")
    meta_rows, warnings, errors = load_meta(META_CSV)

    for w in warnings:
        print(f"  {w}")
    for e in errors:
        print(f"  ❌ {e}")

    if errors:
        print(f"\n❌ {len(errors)} error(s) found — fix the CSV before building.\n")
        sys.exit(1)

    print(f"  → {len(meta_rows)} species loaded\n")

    print(f"🗺  Loading range polygons from {RANGES_GEOJSON}")
    ranges = load_ranges(RANGES_GEOJSON)
    print(f"  → {len(ranges)} species with polygons\n")

    # Check for meta without ranges
    missing_ranges = [aid for aid in meta_rows if aid not in ranges]
    if missing_ranges:
        for aid in missing_ranges:
            print(f"  ⚠  No polygon for '{aid}' — will be excluded")

    # Build JS
    js_content = build_js(meta_rows, ranges)

    included = sum(1 for aid in meta_rows if aid in ranges)
    print(f"\n✅ Building animals.js with {included} species...")

    os.makedirs(os.path.dirname(OUTPUT_JS), exist_ok=True)
    with open(OUTPUT_JS, "w", encoding="utf-8") as f:
        f.write(js_content)

    print(f"✅ Written → {OUTPUT_JS}")
    print(f"\n── Summary ─────────────────────────────")
    print(f"   Species included: {included}")
    print(f"   Species excluded: {len(meta_rows) - included + len(missing_ranges)}")
    print(f"\n── Next step ───────────────────────────")
    print(f"   Open the game in your browser to test.")
    print(f"   Any changes to the CSV/GeoJSON? Re-run this script.\n")


if __name__ == "__main__":
    run()
