"""
fetch_animals.py
────────────────
Step 1 of the Wild Range data pipeline.

Queries GBIF for occurrence points for each species in SPECIES_LIST,
builds alpha-shape (concave hull) range polygons, and writes:

  review/animals_meta.csv      ← edit names, hints, conservation status here
  review/animals_ranges.geojson ← edit/inspect polygons here

Usage:
  python3 fetch_animals.py

Requirements:
  pip install requests shapely numpy pandas scipy

Notes:
  - GBIF data is CC BY 4.0 — attribution required in your app footer.
  - Rate limits: ~1 req/sec is safe; the script respects this automatically.
  - Occurrence points are filtered to human-observation / specimen records
    with coordinate precision ≤ 50 km to reduce noise.
  - Alpha parameter controls polygon tightness. Lower = tighter fit but
    more holes. Adjust per-species in SPECIES_LIST if needed.
"""

import requests
import time
import json
import csv
import math
import sys
import os
from collections import defaultdict

import numpy as np
import pandas as pd
from scipy.spatial import Delaunay
from shapely.geometry import MultiPoint, Polygon, MultiPolygon, mapping
from shapely.ops import unary_union

# ── Output paths ──────────────────────────────────────────────────────────────
REVIEW_DIR   = os.path.join(os.path.dirname(__file__), "review")
META_CSV     = os.path.join(REVIEW_DIR, "animals_meta.csv")
RANGES_GEOJSON = os.path.join(REVIEW_DIR, "animals_ranges.geojson")

# ── GBIF API ──────────────────────────────────────────────────────────────────
GBIF_SPECIES_URL    = "https://api.gbif.org/v1/species/match"
GBIF_OCCURRENCE_URL = "https://api.gbif.org/v1/occurrence/search"
MAX_OCCURRENCES     = 2000   # per species — increase for better polygons, slower fetch
OCCURRENCE_LIMIT    = 300    # per page (GBIF max is 300)
REQUEST_DELAY       = 0.8    # seconds between requests

# ── Alpha shape parameters ────────────────────────────────────────────────────
DEFAULT_ALPHA       = 3.0    # higher = tighter. Override per species below.
MIN_POINTS_FOR_HULL = 8      # minimum occurrences needed to build a polygon
SIMPLIFY_TOLERANCE  = 0.5    # degrees — simplifies polygon for smaller file size
CLUSTER_GAP_DEG     = 25.0   # separate clusters more than this apart into distinct polygons

# ── Species list ──────────────────────────────────────────────────────────────
# Format: (scientific_name, common_name, emoji, hint, iucn_status, alpha_override_or_None)
# iucn_status: CR, EN, VU, NT, LC  (GBIF doesn't have IUCN status reliably,
#              so we set it manually here — cross-reference iucnredlist.org)
# alpha_override: None = use DEFAULT_ALPHA. Set lower (e.g. 1.5) for wide-ranging
#                 species, higher (e.g. 5.0) for tightly clustered ones.

SPECIES_LIST = [
    # Critically Endangered
    ("Panthera tigris altaica",    "Amur Tiger",            "🐯", "The rarest tiger subspecies — fewer than 500 remain in the Russian Far East", "CR", 6.0),
    ("Diceros bicornis",           "Black Rhino",           "🦏", "Critically endangered despite recovery efforts — targeted by poachers for its horn", "CR", 3.0),
    ("Gorilla beringei beringei",  "Mountain Gorilla",      "🦍", "Lives only in two tiny mountain ranges in central Africa", "CR", 8.0),
    ("Phocoena sinus",             "Vaquita",               "🐬", "World's most critically endangered marine mammal — fewer than 10 remain", "CR", 5.0),
    ("Copsychus sechellarum",      "Seychelles Magpie Robin","🐦","Once extinct in the wild — brought back through intensive island management", "CR", 8.0),
    ("Gavialis gangeticus",        "Gharial",               "🐊", "Critically endangered crocodilian — almost entirely aquatic, found in South Asian rivers", "CR", 5.0),

    # Endangered
    ("Panthera tigris tigris",     "Bengal Tiger",          "🐯", "National animal of India — no two have the same stripe pattern", "EN", 3.0),
    ("Gorilla gorilla",            "Western Gorilla",       "🦍", "Largest primate on Earth — lives in the Congo Basin rainforest", "EN", 3.0),
    ("Pongo pygmaeus",             "Bornean Orangutan",     "🦧", "'Person of the forest' — only great ape found in Asia", "EN", 5.0),
    ("Pongo abelii",               "Sumatran Orangutan",    "🦧", "More endangered than its Bornean cousin — restricted to northern Sumatra", "EN", 6.0),
    ("Elephas maximus",            "Asian Elephant",        "🐘", "Smaller ears than African elephants — revered across South and Southeast Asia", "EN", 3.0),
    ("Trichechus manatus",         "West Indian Manatee",   "🐟", "Gentle sea cows — may have inspired mermaid legends among sailors", "EN", 2.5),
    ("Lycaon pictus",              "African Wild Dog",      "🐕", "Most successful hunter in Africa — uses democratic pack decisions to coordinate hunts", "EN", 2.5),
    ("Ailurus fulgens",            "Red Panda",             "🦊", "First animal called 'panda' — not closely related to the giant panda", "EN", 4.0),
    ("Balaenoptera musculus",      "Blue Whale",            "🐋", "Largest animal ever to have lived — its heart is the size of a small car", "EN", 1.5),
    ("Spheniscus demersus",        "African Penguin",       "🐧", "The only penguin species found on the African continent", "EN", 4.0),
    ("Neofelis nebulosa",          "Clouded Leopard",       "🐆", "Has the longest canine teeth relative to body size of any living cat", "EN", 3.5),

    # Vulnerable
    ("Loxodonta africana",         "African Savanna Elephant","🐘","World's largest land animal — uses its trunk as a snorkel while swimming", "VU", 2.0),
    ("Ursus maritimus",            "Polar Bear",            "🐻‍❄️", "Largest land predator — entirely dependent on sea ice to hunt seals", "VU", 2.0),
    ("Panthera onca",              "Jaguar",                "🐆", "Largest cat in the Americas — loves water and hunts fish and caiman", "VU", 2.0),
    ("Panthera uncia",             "Snow Leopard",          "🐆", "Ghost of the mountains — rarely seen, lives at extreme altitudes", "VU", 3.5),
    ("Ailuropoda melanoleuca",     "Giant Panda",           "🐼", "Global symbol of conservation — eats almost nothing but bamboo", "VU", 6.0),
    ("Hippopotamus amphibius",     "Hippopotamus",          "🦛", "Despite looking placid, hippos are Africa's most dangerous large land animal", "VU", 2.5),
    ("Chelonia mydas",             "Green Sea Turtle",      "🐢", "Navigates thousands of miles of open ocean to return to the exact beach where it hatched", "VU", 1.5),
    ("Acinonyx jubatus",           "Cheetah",               "🐆", "Fastest land animal — needs 30 minutes to recover after a sprint before it can eat", "VU", 2.5),
    ("Carcharodon carcharias",     "Great White Shark",     "🦈", "Feared but vulnerable — slow to reproduce and threatened by finning and bycatch", "VU", 1.5),
    ("Apteryx australis",          "Brown Kiwi",            "🥝", "Flightless bird with nostrils at the tip of its beak — sniffs out earthworms underground", "VU", 5.0),
    ("Tapirus terrestris",         "South American Tapir",  "🐗", "Living fossil — one of South America's oldest mammal lineages", "VU", 2.5),
    ("Varanus komodoensis",        "Komodo Dragon",         "🦎", "World's largest lizard — found only on a handful of Indonesian islands", "VU", 7.0),
    ("Saiga tatarica",             "Saiga Antelope",        "🦌", "Prehistoric-looking nose filters dust on the open steppes of Central Asia", "CR", 3.0),

    # Near Threatened
    ("Panthera leo",               "African Lion",          "🦁", "Social big cat — the only one that lives in groups called prides", "VU", 2.5),
    ("Orcinus orca",               "Orca",                  "🐳", "Apex predator of every ocean — intelligent enough to teach hunting techniques across generations", "DD", 1.5),
    ("Giraffe camelopardalis",     "Giraffe",               "🦒", "Tallest animal on Earth — its heart must pump blood nearly 8 feet up to reach its brain", "VU", 2.5),
    ("Mandrillus sphinx",          "Mandrill",              "🐒", "World's largest monkey — males have vivid blue and red faces", "VU", 4.0),
    ("Tursiops truncatus",         "Bottlenose Dolphin",    "🐬", "Among the most intelligent animals — can recognize themselves in mirrors", "LC", 1.5),

    # Least Concern (but ecologically important or interesting)
    ("Haliaeetus leucocephalus",   "Bald Eagle",            "🦅", "National bird of the USA — once nearly wiped out by DDT, now a conservation success story", "LC", 2.0),
    ("Macropus rufus",             "Red Kangaroo",          "🦘", "Australia's largest native land animal — can leap 30 feet in a single bound", "LC", 3.0),
    ("Ailurus fulgens",            "Red Panda",             "🦊", "First animal called 'panda' — not closely related to the giant panda", "EN", 4.0),
    ("Canis lupus",                "Gray Wolf",             "🐺", "Keystone predator — its presence or absence reshapes entire ecosystems", "LC", 2.0),
    ("Ursus arctos",               "Brown Bear",            "🐻", "Found on four continents — populations range from tiny Kodiak islands to vast Siberian forests", "LC", 2.0),
    ("Meleagris gallopavo",        "Wild Turkey",           "🦃", "The original wild bird — Benjamin Franklin reportedly preferred it over the eagle as a national symbol", "LC", 3.0),
    ("Dromaius novaehollandiae",   "Emu",                   "🐦", "Australia's tallest bird — it lost a war against humans in 1932", "LC", 2.5),
    ("Pan troglodytes",            "Chimpanzee",            "🐒", "Humans' closest living relative — uses tools, mourns its dead, and wages war", "EN", 3.0),
    ("Equus quagga",               "Plains Zebra",          "🦓", "Each zebra's stripe pattern is unique — like a fingerprint", "NT", 2.5),
    ("Syncerus caffer",            "African Buffalo",       "🐃", "Never domesticated — has killed more hunters in Africa than any other animal", "NT", 2.5),
    ("Crocodylus niloticus",       "Nile Crocodile",        "🐊", "One of Africa's apex predators — can hold its breath for over an hour", "LC", 2.5),
    ("Phoenicopterus roseus",      "Greater Flamingo",      "🦩", "Gets its pink color entirely from the carotenoid pigments in its food", "LC", 2.0),
    ("Phascolarctos cinereus",     "Koala",                 "🐨", "Sleeps up to 22 hours a day — eucalyptus leaves are so low in nutrients it must conserve every calorie", "VU", 4.0),
    ("Suricata suricatta",         "Meerkat",               "🦦", "Lives in highly organized groups with dedicated sentinels that warn the mob of predators", "LC", 4.0),
]

# Deduplicate by scientific name
seen = set()
SPECIES_LIST = [s for s in SPECIES_LIST if s[0] not in seen and not seen.add(s[0])]


# ── Alpha shape algorithm ─────────────────────────────────────────────────────

def alpha_shape(points, alpha):
    """
    Compute the alpha shape (concave hull) of a set of 2D points.
    Returns a Shapely geometry (Polygon or MultiPolygon).
    Falls back to convex hull if not enough points or alpha too tight.
    """
    if len(points) < 4:
        return MultiPoint(points).convex_hull

    coords = np.array(points)
    try:
        tri = Delaunay(coords)
    except Exception:
        return MultiPoint(list(map(tuple, coords))).convex_hull

    triangles = coords[tri.simplices]
    edge_set = set()
    keep = []

    for tri_pts in triangles:
        # Circumradius of the triangle
        a = np.linalg.norm(tri_pts[0] - tri_pts[1])
        b = np.linalg.norm(tri_pts[1] - tri_pts[2])
        c = np.linalg.norm(tri_pts[2] - tri_pts[0])
        denom = a * b * c
        if denom == 0:
            continue
        s = (a + b + c) / 2
        area = max(s * (s-a) * (s-b) * (s-c), 0) ** 0.5
        if area == 0:
            continue
        circumradius = denom / (4 * area)
        if circumradius < 1.0 / alpha:
            keep.append(tri_pts)

    if not keep:
        # Alpha too tight — fall back to convex hull
        return MultiPoint(list(map(tuple, coords))).convex_hull

    # Build edge boundary
    edge_count = defaultdict(int)
    for tri_pts in keep:
        for i in range(3):
            edge = tuple(sorted([tuple(tri_pts[i]), tuple(tri_pts[(i+1)%3])]))
            edge_count[edge] += 1

    boundary_edges = [e for e, cnt in edge_count.items() if cnt == 1]
    if not boundary_edges:
        return MultiPoint(list(map(tuple, coords))).convex_hull

    # Stitch boundary edges into ring(s)
    edge_map = defaultdict(list)
    for a_pt, b_pt in boundary_edges:
        edge_map[a_pt].append(b_pt)
        edge_map[b_pt].append(a_pt)

    polygons = []
    visited_edges = set()

    for start in edge_map:
        if all(tuple(sorted([start, nb])) in visited_edges for nb in edge_map[start]):
            continue
        ring = [start]
        current = start
        prev = None
        for _ in range(len(boundary_edges) + 1):
            neighbors = [n for n in edge_map[current] if n != prev]
            if not neighbors:
                break
            nxt = neighbors[0]
            edge_key = tuple(sorted([current, nxt]))
            if edge_key in visited_edges:
                break
            visited_edges.add(edge_key)
            ring.append(nxt)
            prev, current = current, nxt
            if current == start:
                break

        if len(ring) >= 4:
            try:
                poly = Polygon(ring)
                if poly.is_valid and poly.area > 0:
                    polygons.append(poly)
            except Exception:
                pass

    if not polygons:
        return MultiPoint(list(map(tuple, coords))).convex_hull

    result = unary_union(polygons)
    return result


def cluster_points(points, gap_deg):
    """
    Split points into geographic clusters separated by more than gap_deg degrees.
    Uses simple single-linkage approach on longitude gaps after sorting.
    """
    if not points:
        return []

    # Sort by longitude
    pts = sorted(points, key=lambda p: p[0])

    clusters = [[pts[0]]]
    for pt in pts[1:]:
        # Check distance to any point in last cluster
        min_dist = min(
            math.sqrt((pt[0]-cp[0])**2 + (pt[1]-cp[1])**2)
            for cp in clusters[-1]
        )
        if min_dist > gap_deg:
            clusters.append([pt])
        else:
            clusters[-1].append(pt)

    return clusters


# ── GBIF fetch ────────────────────────────────────────────────────────────────

def get_gbif_taxon_key(scientific_name):
    """Resolve a scientific name to a GBIF taxon key."""
    try:
        r = requests.get(GBIF_SPECIES_URL, params={"name": scientific_name, "verbose": False}, timeout=10)
        r.raise_for_status()
        data = r.json()
        key = data.get("usageKey") or data.get("speciesKey")
        match_type = data.get("matchType", "NONE")
        if match_type == "NONE":
            return None, f"No match found"
        return key, data.get("canonicalName", scientific_name)
    except Exception as e:
        return None, str(e)


def fetch_occurrences(taxon_key, max_records=MAX_OCCURRENCES):
    """
    Fetch occurrence records from GBIF for a taxon key.
    Returns list of (lng, lat) tuples.
    """
    points = []
    offset = 0

    while len(points) < max_records:
        params = {
            "taxonKey":          taxon_key,
            "hasCoordinate":     "true",
            "hasGeospatialIssue":"false",
            "occurrenceStatus":  "PRESENT",
            "basisOfRecord":     "HUMAN_OBSERVATION,MACHINE_OBSERVATION,PRESERVED_SPECIMEN,LITERATURE",
            "coordinateUncertaintyInMeters": "0,50000",
            "limit":             OCCURRENCE_LIMIT,
            "offset":            offset,
            "fields":            "decimalLongitude,decimalLatitude",
        }
        try:
            r = requests.get(GBIF_OCCURRENCE_URL, params=params, timeout=20)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"    ⚠  Request failed: {e}")
            break

        results = data.get("results", [])
        if not results:
            break

        for rec in results:
            lat = rec.get("decimalLatitude")
            lng = rec.get("decimalLongitude")
            if lat is not None and lng is not None:
                if -90 <= lat <= 90 and -180 <= lng <= 180:
                    points.append((lng, lat))

        offset += len(results)
        if data.get("endOfRecords", True):
            break

        time.sleep(REQUEST_DELAY)

    return points


def build_range_polygons(points, alpha, name):
    """
    Given occurrence (lng,lat) points, build alpha-shape polygon(s).
    Returns list of GeoJSON-compatible polygon coordinate arrays.
    """
    if len(points) < MIN_POINTS_FOR_HULL:
        print(f"    ⚠  Only {len(points)} points — skipping polygon (need {MIN_POINTS_FOR_HULL}+)")
        return []

    # Cluster by geography to handle disjoint ranges (e.g. cheetah in Africa + Iran)
    clusters = cluster_points(points, CLUSTER_GAP_DEG)
    print(f"    → {len(points)} points in {len(clusters)} cluster(s)")

    geojson_polys = []

    for cluster_pts in clusters:
        if len(cluster_pts) < MIN_POINTS_FOR_HULL:
            continue

        shape = alpha_shape(cluster_pts, alpha)
        if shape is None or shape.is_empty:
            continue

        # Simplify
        shape = shape.simplify(SIMPLIFY_TOLERANCE, preserve_topology=True)

        # Normalize to MultiPolygon
        if isinstance(shape, Polygon):
            shape = MultiPolygon([shape])
        elif not isinstance(shape, MultiPolygon):
            # Could be LineString, Point, etc. if degenerate
            continue

        for poly in shape.geoms:
            if poly.is_empty or poly.area < 0.01:
                continue
            # GeoJSON exterior ring (drop holes for simplicity)
            coords = list(poly.exterior.coords)
            # Convert to {lat, lng} format used by the game
            geojson_polys.append([[round(c[1], 4), round(c[0], 4)] for c in coords])

    return geojson_polys


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run():
    os.makedirs(REVIEW_DIR, exist_ok=True)

    meta_rows = []
    features  = []
    skipped   = []

    total = len(SPECIES_LIST)
    print(f"\n🌿 Wild Range — GBIF fetch pipeline")
    print(f"   Processing {total} species...\n")

    for i, (sci_name, common_name, emoji, hint, status, alpha_override) in enumerate(SPECIES_LIST):
        alpha = alpha_override if alpha_override is not None else DEFAULT_ALPHA
        print(f"[{i+1}/{total}] {common_name} ({sci_name})")

        # 1. Resolve taxon key
        taxon_key, resolved_name = get_gbif_taxon_key(sci_name)
        time.sleep(REQUEST_DELAY)

        if not taxon_key:
            print(f"    ✗ Could not resolve: {resolved_name}")
            skipped.append((sci_name, common_name, resolved_name))
            continue

        print(f"    ✓ Taxon key: {taxon_key} ({resolved_name})")

        # 2. Fetch occurrences
        points = fetch_occurrences(taxon_key)
        print(f"    ✓ {len(points)} occurrences fetched")

        if len(points) < MIN_POINTS_FOR_HULL:
            print(f"    ✗ Too few points — skipped")
            skipped.append((sci_name, common_name, f"Only {len(points)} occurrences"))
            continue

        # 3. Build alpha-shape polygon
        polys = build_range_polygons(points, alpha, common_name)

        if not polys:
            print(f"    ✗ Could not build polygon — skipped")
            skipped.append((sci_name, common_name, "Polygon build failed"))
            continue

        print(f"    ✓ Built {len(polys)} polygon(s)")

        # 4. Build animal ID
        animal_id = common_name.lower().replace(" ", "-").replace("'","")

        # 5. Meta row (for CSV)
        meta_rows.append({
            "id":            animal_id,
            "scientific_name": sci_name,
            "name":          common_name,
            "emoji":         emoji,
            "hint":          hint,
            "status":        status,
            "region":        "",          # fill in manually or leave blank
            "fact":          "",          # fill in manually
            "alpha_used":    alpha,
            "point_count":   len(points),
            "polygon_count": len(polys),
            "include":       "yes",       # set to "no" to exclude from final build
        })

        # 6. GeoJSON feature
        features.append({
            "type": "Feature",
            "properties": {
                "id":     animal_id,
                "name":   common_name,
                "status": status,
            },
            "geometry": {
                "type": "MultiPolygon",
                # GeoJSON uses [lng, lat] — we store [[lat,lng]...] internally,
                # so convert here for valid GeoJSON
                "coordinates": [
                    [[[pt[1], pt[0]] for pt in poly]]   # exterior ring only
                    for poly in polys
                ]
            }
        })

        time.sleep(REQUEST_DELAY)

    # ── Write outputs ──────────────────────────────────────────────────────────

    # CSV
    if meta_rows:
        fieldnames = list(meta_rows[0].keys())
        with open(META_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(meta_rows)
        print(f"\n✅ Metadata written → {META_CSV}")

    # GeoJSON
    geojson = {"type": "FeatureCollection", "features": features}
    with open(RANGES_GEOJSON, "w", encoding="utf-8") as f:
        json.dump(geojson, f, indent=2)
    print(f"✅ Ranges written    → {RANGES_GEOJSON}")

    # Summary
    print(f"\n── Summary ─────────────────────────────")
    print(f"   Succeeded: {len(meta_rows)}")
    print(f"   Skipped:   {len(skipped)}")
    if skipped:
        print("   Skipped species:")
        for sci, common, reason in skipped:
            print(f"     • {common} ({sci}) — {reason}")

    print(f"\n── Next steps ──────────────────────────")
    print(f"   1. Open review/animals_meta.csv and fill in 'fact' and 'region' columns.")
    print(f"      Set 'include' to 'no' for any species you want to exclude.")
    print(f"   2. Inspect review/animals_ranges.geojson at https://geojson.io")
    print(f"      to visually verify and edit polygons if needed.")
    print(f"   3. Run:  python3 build_animals_js.py")
    print(f"      to generate data/animals.js for the game.\n")


if __name__ == "__main__":
    run()
