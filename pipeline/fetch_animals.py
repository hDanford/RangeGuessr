"""
fetch_animals.py  —  Wild Range data pipeline, Step 1
──────────────────────────────────────────────────────
Queries GBIF for each species in SPECIES_LIST:
  • Occurrence points → alpha-shape range polygons
  • Media endpoint   → best available CC-licensed photo URL

Writes:
  review/animals_meta.csv        ← edit names, hints, status, fact, region here
  review/animals_ranges.geojson  ← inspect/edit polygons at geojson.io
  review/animals_images.json     ← image URLs; swap any you don't like

Then run:  python3 build_animals_js.py

Requirements:
  pip install requests shapely numpy pandas scipy

Attribution (required in your app):
  Occurrence data + images: GBIF.org (CC BY 4.0)
"""

import requests, time, json, csv, math, os, sys
from collections import defaultdict
import numpy as np
from scipy.spatial import Delaunay
from shapely.geometry import MultiPoint, Polygon, MultiPolygon, mapping
from shapely.ops import unary_union

# ── Paths ─────────────────────────────────────────────────────────────────────
REVIEW_DIR     = os.path.join(os.path.dirname(__file__), "review")
META_CSV       = os.path.join(REVIEW_DIR, "animals_meta.csv")
RANGES_GEOJSON = os.path.join(REVIEW_DIR, "animals_ranges.geojson")
IMAGES_JSON    = os.path.join(REVIEW_DIR, "animals_images.json")

# ── GBIF settings ─────────────────────────────────────────────────────────────
GBIF_MATCH      = "https://api.gbif.org/v1/species/match"
GBIF_OCC        = "https://api.gbif.org/v1/occurrence/search"
GBIF_MEDIA      = "https://api.gbif.org/v1/species/{key}/media"
MAX_OCCURRENCES = 2000
OCC_PAGE_SIZE   = 300
DELAY           = 0.8   # seconds between requests

# ── Alpha shape settings ──────────────────────────────────────────────────────
DEFAULT_ALPHA    = 3.0
MIN_POINTS       = 8
SIMPLIFY_TOL     = 0.5
CLUSTER_GAP_DEG  = 25.0

# ── Preferred CC licenses (in priority order) ─────────────────────────────────
# All of these allow commercial use with attribution
GOOD_LICENSES = [
    "http://creativecommons.org/licenses/by/4.0/",
    "http://creativecommons.org/licenses/by/3.0/",
    "http://creativecommons.org/licenses/by-sa/4.0/",
    "http://creativecommons.org/licenses/by-sa/3.0/",
    "http://creativecommons.org/publicdomain/zero/1.0/",
    "https://creativecommons.org/licenses/by/4.0/",
    "https://creativecommons.org/licenses/by/3.0/",
    "https://creativecommons.org/licenses/by-sa/4.0/",
    "https://creativecommons.org/licenses/by-sa/3.0/",
    "https://creativecommons.org/publicdomain/zero/1.0/",
    "http://creativecommons.org/licenses/by-nc/4.0/",   # NC ok if non-commercial fallback
]

# ── Species list ──────────────────────────────────────────────────────────────
# (scientific_name, common_name, emoji, hint, iucn_status, alpha)
SPECIES_LIST = [
    # Critically Endangered
    ("Panthera tigris altaica",     "Amur Tiger",               "🐯", "Rarest tiger subspecies — fewer than 500 survive in Russia's Far East", "CR", 6.0),
    ("Diceros bicornis",            "Black Rhinoceros",         "🦏", "Critically endangered despite recovery — targeted by poachers for its horn", "CR", 3.0),
    ("Gorilla beringei beringei",   "Mountain Gorilla",         "🦍", "Lives only in two tiny mountain ranges in central Africa", "CR", 8.0),
    ("Phocoena sinus",              "Vaquita",                  "🐬", "World's most critically endangered marine mammal — fewer than 10 remain", "CR", 5.0),
    ("Gavialis gangeticus",         "Gharial",                  "🐊", "Critically endangered crocodilian with a long, thin snout for catching fish", "CR", 5.0),
    ("Saiga tatarica",              "Saiga Antelope",           "🦌", "Prehistoric-looking bulbous nose filters dust on the Central Asian steppes", "CR", 3.0),
    ("Spheniscus demersus",         "African Penguin",          "🐧", "The only penguin on the African continent — its population has collapsed 70% since 1970", "EN", 4.0),
    ("Pongo abelii",                "Sumatran Orangutan",       "🦧", "More endangered than its Bornean cousin — restricted to northern Sumatra", "CR", 6.0),
    ("Rhincodon typus",             "Whale Shark",              "EN", "🦈", "Largest fish on Earth — filter feeds on tiny plankton despite its enormous size", 1.5),
    ("Chelonia mydas",              "Green Sea Turtle",         "🐢", "Navigates thousands of miles of open ocean to return to the exact beach where it hatched", "EN", 1.5),

    # Endangered
    ("Panthera tigris tigris",      "Bengal Tiger",             "🐯", "National animal of India — no two have the same stripe pattern", "EN", 3.0),
    ("Gorilla gorilla",             "Western Gorilla",          "🦍", "Largest primate on Earth — lives in the Congo Basin rainforest", "EN", 3.0),
    ("Pongo pygmaeus",              "Bornean Orangutan",        "🦧", "'Person of the forest' — only great ape found in Asia", "EN", 5.0),
    ("Elephas maximus",             "Asian Elephant",           "🐘", "Smaller ears than African elephants — revered across South and Southeast Asia", "EN", 3.0),
    ("Trichechus manatus",          "West Indian Manatee",      "🐟", "Gentle sea cows that may have inspired mermaid legends among sailors", "VU", 2.5),
    ("Lycaon pictus",               "African Wild Dog",         "🐕", "Most successful hunter in Africa — uses democratic sneezing to vote on pack decisions", "EN", 2.5),
    ("Ailurus fulgens",             "Red Panda",                "🦊", "The first animal ever called 'panda' — not closely related to the giant panda", "EN", 4.0),
    ("Balaenoptera musculus",       "Blue Whale",               "🐋", "Largest animal to have ever lived — its heart is the size of a small car", "EN", 1.5),
    ("Neofelis nebulosa",           "Clouded Leopard",          "🐆", "Has the longest canine teeth relative to body size of any living cat", "VU", 3.5),
    ("Tapirus terrestris",          "South American Tapir",     "🐗", "Living fossil — one of South America's oldest mammal lineages", "VU", 2.5),
    ("Pan troglodytes",             "Chimpanzee",               "🐒", "Humans' closest living relative — uses tools, mourns its dead, and wages war", "EN", 3.0),
    ("Hippocampus guttulatus",      "Long-Snouted Seahorse",    "🐠", "Males carry and give birth to the young — one of the few animals where fathers give birth", "VU", 3.0),

    # Vulnerable
    ("Loxodonta africana",          "African Savanna Elephant", "🐘", "World's largest land animal — uses its trunk as a snorkel while swimming", "VU", 2.0),
    ("Ursus maritimus",             "Polar Bear",               "🐻‍❄️", "Largest land predator — entirely dependent on Arctic sea ice to hunt seals", "VU", 2.0),
    ("Panthera onca",               "Jaguar",                   "🐆", "Largest cat in the Americas — loves water and actively hunts fish and caiman", "VU", 2.0),
    ("Panthera uncia",              "Snow Leopard",             "🐆", "Ghost of the mountains — rarely seen even by researchers, lives at extreme altitude", "VU", 3.5),
    ("Ailuropoda melanoleuca",      "Giant Panda",              "🐼", "Global symbol of conservation — eats almost nothing but bamboo", "VU", 6.0),
    ("Hippopotamus amphibius",      "Hippopotamus",             "🦛", "Despite looking placid, hippos kill more people in Africa than any other large animal", "VU", 2.5),
    ("Acinonyx jubatus",            "Cheetah",                  "🐆", "Fastest land animal — needs 30 minutes to recover after a sprint before it can eat", "VU", 2.5),
    ("Carcharodon carcharias",      "Great White Shark",        "🦈", "Feared but vulnerable — slow to reproduce and threatened by finning and bycatch", "VU", 1.5),
    ("Apteryx australis",           "Brown Kiwi",               "🥝", "Flightless bird with nostrils at the beak tip — sniffs earthworms underground", "VU", 5.0),
    ("Varanus komodoensis",         "Komodo Dragon",            "🦎", "World's largest lizard — found only on a handful of Indonesian islands", "VU", 7.0),
    ("Phascolarctos cinereus",      "Koala",                    "🐨", "Sleeps 22 hours a day — eucalyptus leaves are so toxic and low-calorie it must conserve every calorie", "VU", 4.0),
    ("Mandrillus sphinx",           "Mandrill",                 "🐒", "World's largest monkey — males have vivid blue and red faces", "VU", 4.0),
    ("Ursus arctos horribilis",     "Grizzly Bear",             "🐻", "Keystone species — their salmon fishing fertilizes entire forests with ocean nutrients", "LC", 2.5),

    # Near Threatened
    ("Panthera leo",                "African Lion",             "🦁", "The only social big cat — lives in groups called prides", "VU", 2.5),
    ("Giraffe camelopardalis",      "Giraffe",                  "🦒", "Tallest animal on Earth — its heart must pump blood nearly 8 feet up to reach its brain", "VU", 2.5),
    ("Equus quagga",                "Plains Zebra",             "🦓", "Each zebra's stripe pattern is as unique as a fingerprint", "NT", 2.5),
    ("Syncerus caffer",             "African Buffalo",          "🐃", "Never domesticated — has killed more hunters in Africa than any other animal", "NT", 2.5),

    # Least Concern (ecologically important or charismatic)
    ("Haliaeetus leucocephalus",    "Bald Eagle",               "🦅", "National bird of the USA — nearly wiped out by DDT, now a conservation success story", "LC", 2.0),
    ("Macropus rufus",              "Red Kangaroo",             "🦘", "Australia's largest native land animal — can leap 30 feet in a single bound", "LC", 3.0),
    ("Canis lupus",                 "Gray Wolf",                "🐺", "Keystone predator — its presence or absence reshapes entire ecosystems", "LC", 2.0),
    ("Ursus arctos",                "Brown Bear",               "🐻", "Found on four continents — one of Earth's most wide-ranging land predators", "LC", 2.0),
    ("Dromaius novaehollandiae",    "Emu",                      "🐦", "Australia's tallest bird — it famously won a war against the Australian Army in 1932", "LC", 2.5),
    ("Phoenicopterus roseus",       "Greater Flamingo",         "🦩", "Gets its pink color entirely from pigments in its food — a white flamingo is a malnourished one", "LC", 2.0),
    ("Suricata suricatta",          "Meerkat",                  "🦦", "Lives in highly organized mobs with dedicated sentinels that warn the group of predators", "LC", 4.0),
    ("Crocodylus niloticus",        "Nile Crocodile",           "🐊", "One of Africa's apex predators — can hold its breath for over an hour underwater", "LC", 2.5),
    ("Struthio camelus",            "Ostrich",                  "🐦", "World's largest bird and fastest two-legged animal — can run at 45 mph", "LC", 2.5),
    ("Tursiops truncatus",          "Bottlenose Dolphin",       "🐬", "Among the most intelligent animals — can recognize themselves in mirrors and learn by watching", "LC", 1.5),
    ("Orcinus orca",                "Orca",                     "🐳", "Apex predator of every ocean — intelligent enough to teach unique hunting techniques to offspring", "DD", 1.5),
    ("Gorilla beringei",            "Eastern Gorilla",          "🦍", "Largest living primate — a silverback male can be six times stronger than a human", "CR", 3.5),
    ("Panthera pardus",             "Leopard",                  "🐆", "Most adaptable of the big cats — found from African rainforests to Siberian snow", "VU", 2.5),
]

# Deduplicate
seen = set()
SPECIES_LIST = [s for s in SPECIES_LIST if s[0] not in seen and not seen.add(s[0])]


# ── Alpha shape ───────────────────────────────────────────────────────────────
def alpha_shape(points, alpha):
    if len(points) < 4:
        return MultiPoint(points).convex_hull
    coords = np.array(points)
    try:
        tri = Delaunay(coords)
    except Exception:
        return MultiPoint(list(map(tuple, coords))).convex_hull

    edge_count = defaultdict(int)
    keep = []
    for simplex in tri.simplices:
        pts = coords[simplex]
        a = np.linalg.norm(pts[0]-pts[1])
        b = np.linalg.norm(pts[1]-pts[2])
        c = np.linalg.norm(pts[2]-pts[0])
        s = (a+b+c)/2
        area = max(s*(s-a)*(s-b)*(s-c), 0)**0.5
        if area == 0: continue
        if (a*b*c)/(4*area) < 1.0/alpha:
            keep.append(pts)
            for i in range(3):
                edge = tuple(sorted([tuple(pts[i]), tuple(pts[(i+1)%3])]))
                edge_count[edge] += 1

    if not keep:
        return MultiPoint(list(map(tuple, coords))).convex_hull

    boundary = [e for e,cnt in edge_count.items() if cnt==1]
    if not boundary:
        return MultiPoint(list(map(tuple, coords))).convex_hull

    edge_map = defaultdict(list)
    for a,b in boundary:
        edge_map[a].append(b); edge_map[b].append(a)

    polygons = []
    visited = set()
    for start in edge_map:
        if all(tuple(sorted([start,nb])) in visited for nb in edge_map[start]):
            continue
        ring = [start]; cur = start; prev = None
        for _ in range(len(boundary)+1):
            nbs = [n for n in edge_map[cur] if n != prev]
            if not nbs: break
            nxt = nbs[0]
            key = tuple(sorted([cur,nxt]))
            if key in visited: break
            visited.add(key)
            ring.append(nxt); prev,cur = cur,nxt
            if cur == start: break
        if len(ring) >= 4:
            try:
                p = Polygon(ring)
                if p.is_valid and p.area > 0: polygons.append(p)
            except: pass

    if not polygons:
        return MultiPoint(list(map(tuple, coords))).convex_hull
    return unary_union(polygons)


def cluster_points(points, gap):
    if not points: return []
    pts = sorted(points, key=lambda p: p[0])
    clusters = [[pts[0]]]
    for pt in pts[1:]:
        d = min(math.sqrt((pt[0]-cp[0])**2+(pt[1]-cp[1])**2) for cp in clusters[-1])
        if d > gap: clusters.append([pt])
        else: clusters[-1].append(pt)
    return clusters


def build_range_polygons(points, alpha, name):
    if len(points) < MIN_POINTS:
        print(f"    ⚠  Only {len(points)} points — skipping")
        return []
    clusters = cluster_points(points, CLUSTER_GAP_DEG)
    print(f"    → {len(points)} pts in {len(clusters)} cluster(s)")
    result = []
    for cluster in clusters:
        if len(cluster) < MIN_POINTS: continue
        shape = alpha_shape(cluster, alpha)
        if not shape or shape.is_empty: continue
        shape = shape.simplify(SIMPLIFY_TOL, preserve_topology=True)
        if isinstance(shape, Polygon): shape = MultiPolygon([shape])
        elif not isinstance(shape, MultiPolygon): continue
        for poly in shape.geoms:
            if poly.is_empty or poly.area < 0.01: continue
            coords = list(poly.exterior.coords)
            result.append([[round(c[1],4), round(c[0],4)] for c in coords])
    return result


# ── GBIF fetchers ─────────────────────────────────────────────────────────────
def get_taxon_key(sci_name):
    try:
        r = requests.get(GBIF_MATCH, params={"name": sci_name, "verbose": False}, timeout=10)
        r.raise_for_status()
        d = r.json()
        if d.get("matchType") == "NONE": return None, "No match"
        return d.get("usageKey") or d.get("speciesKey"), d.get("canonicalName", sci_name)
    except Exception as e:
        return None, str(e)


def fetch_occurrences(taxon_key):
    points = []; offset = 0
    while len(points) < MAX_OCCURRENCES:
        params = {
            "taxonKey": taxon_key, "hasCoordinate": "true",
            "hasGeospatialIssue": "false", "occurrenceStatus": "PRESENT",
            "basisOfRecord": "HUMAN_OBSERVATION,MACHINE_OBSERVATION,PRESERVED_SPECIMEN,LITERATURE",
            "coordinateUncertaintyInMeters": "0,50000",
            "limit": OCC_PAGE_SIZE, "offset": offset,
        }
        try:
            r = requests.get(GBIF_OCC, params=params, timeout=20)
            r.raise_for_status()
            d = r.json()
        except Exception as e:
            print(f"    ⚠  {e}"); break
        for rec in d.get("results", []):
            lat = rec.get("decimalLatitude"); lng = rec.get("decimalLongitude")
            if lat is not None and lng is not None and -90<=lat<=90 and -180<=lng<=180:
                points.append((lng, lat))
        offset += len(d.get("results", []))
        if d.get("endOfRecords", True): break
        time.sleep(DELAY)
    return points


def fetch_best_image(taxon_key, common_name):
    """
    Fetch the best CC-licensed image from GBIF species media endpoint.
    Returns dict with url, license, rightsHolder, or None.
    """
    try:
        url = GBIF_MEDIA.format(key=taxon_key)
        r = requests.get(url, params={"limit": 25, "type": "StillImage"}, timeout=10)
        r.raise_for_status()
        results = r.json().get("results", [])
    except Exception as e:
        print(f"    ⚠  Media fetch failed: {e}")
        return None

    # Score each image — prefer good licenses, larger images, iNaturalist source
    best = None
    best_score = -1

    for m in results:
        if m.get("type") != "StillImage": continue
        img_url = m.get("identifier", "")
        if not img_url: continue
        license_url = (m.get("license") or "").lower().rstrip("/")
        rights = m.get("rightsHolder", "")
        source = m.get("references", "")

        # Score by license quality
        license_score = 0
        for i, good in enumerate(GOOD_LICENSES):
            if good.rstrip("/") in license_url:
                license_score = len(GOOD_LICENSES) - i
                break
        if license_score == 0: continue  # skip NC or no-license

        # Prefer iNaturalist (high quality photos)
        source_score = 2 if "inaturalist" in source.lower() else 1

        score = license_score * 10 + source_score
        if score > best_score:
            best_score = score
            best = {
                "url":          img_url,
                "license":      m.get("license", ""),
                "rightsHolder": rights,
                "source":       source,
            }

    if best:
        print(f"    ✓ Image found ({best['license'].split('/')[-2] if '/' in best['license'] else 'CC'})")
    else:
        print(f"    ⚠  No suitable CC image found")

    return best


# ── Main ──────────────────────────────────────────────────────────────────────
def run():
    os.makedirs(REVIEW_DIR, exist_ok=True)

    # Load existing data to avoid re-fetching
    existing_ranges = {}
    existing_images = {}
    existing_meta   = {}

    if os.path.exists(RANGES_GEOJSON):
        with open(RANGES_GEOJSON) as f:
            gj = json.load(f)
        for feat in gj.get("features", []):
            existing_ranges[feat["properties"]["id"]] = feat

    if os.path.exists(IMAGES_JSON):
        with open(IMAGES_JSON) as f:
            existing_images = json.load(f)

    if os.path.exists(META_CSV):
        with open(META_CSV, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                existing_meta[row["id"]] = row

    meta_rows  = dict(existing_meta)
    features   = list(existing_ranges.values())
    images     = dict(existing_images)
    skipped    = []
    total      = len(SPECIES_LIST)

    print(f"\n🌿 Wild Range — GBIF fetch pipeline")
    print(f"   {total} species • skipping already-fetched\n")

    for i, entry in enumerate(SPECIES_LIST):
        sci_name, common_name, emoji, hint, status, alpha = entry[:6]
        animal_id = common_name.lower().replace(" ", "-").replace("'","").replace("é","e")

        already_has_range = animal_id in existing_ranges
        already_has_image = animal_id in existing_images
        already_has_meta  = animal_id in existing_meta

        if already_has_range and already_has_image and already_has_meta:
            print(f"[{i+1}/{total}] ⏭  {common_name} (already complete)")
            continue

        print(f"[{i+1}/{total}] {common_name} ({sci_name})")

        # Resolve taxon key
        taxon_key, resolved = get_taxon_key(sci_name)
        time.sleep(DELAY)
        if not taxon_key:
            print(f"    ✗ Could not resolve: {resolved}")
            skipped.append((common_name, resolved))
            continue
        print(f"    ✓ Key: {taxon_key}")

        # Fetch range
        if not already_has_range:
            points = fetch_occurrences(taxon_key)
            print(f"    ✓ {len(points)} occurrences")
            polys = build_range_polygons(points, alpha, common_name)
            if not polys:
                print(f"    ✗ No polygon built")
                skipped.append((common_name, "polygon failed"))
            else:
                print(f"    ✓ {len(polys)} polygon(s)")
                features = [f for f in features if f["properties"]["id"] != animal_id]
                features.append({
                    "type": "Feature",
                    "properties": {"id": animal_id, "name": common_name, "status": status},
                    "geometry": {
                        "type": "MultiPolygon",
                        "coordinates": [[[[pt[1],pt[0]] for pt in poly]] for poly in polys]
                    }
                })
            time.sleep(DELAY)

        # Fetch image
        if not already_has_image:
            img = fetch_best_image(taxon_key, common_name)
            if img:
                images[animal_id] = img
            time.sleep(DELAY)

        # Meta
        if not already_has_meta:
            meta_rows[animal_id] = {
                "id":              animal_id,
                "scientific_name": sci_name,
                "name":            common_name,
                "emoji":           emoji,
                "hint":            hint,
                "status":          status,
                "region":          "",
                "fact":            "",
                "alpha_used":      alpha,
                "include":         "yes",
            }

        # Save incrementally after each species
        _write_outputs(meta_rows, features, images)

    # Final write
    _write_outputs(meta_rows, features, images)

    print(f"\n── Summary ─────────────────────────────────")
    print(f"   Total species:  {len(meta_rows)}")
    print(f"   With range:     {len([f for f in features if f['properties']['id'] in meta_rows])}")
    print(f"   With image:     {len(images)}")
    print(f"   Skipped:        {len(skipped)}")
    if skipped:
        for name, reason in skipped:
            print(f"     • {name}: {reason}")
    print(f"\n── Next steps ──────────────────────────────")
    print(f"   1. Fill in 'fact' and 'region' in review/animals_meta.csv")
    print(f"   2. Inspect polygons at geojson.io")
    print(f"   3. Check images in review/animals_images.json — swap any URLs you don't like")
    print(f"   4. Run:  python3 build_animals_js.py\n")


def _write_outputs(meta_rows, features, images):
    if meta_rows:
        with open(META_CSV, "w", newline="", encoding="utf-8") as f:
            fieldnames = ["id","scientific_name","name","emoji","hint","status","region","fact","alpha_used","include"]
            w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            w.writeheader(); w.writerows(meta_rows.values())

    with open(RANGES_GEOJSON, "w", encoding="utf-8") as f:
        json.dump({"type":"FeatureCollection","features":features}, f, indent=2)

    with open(IMAGES_JSON, "w", encoding="utf-8") as f:
        json.dump(images, f, indent=2)


if __name__ == "__main__":
    run()
