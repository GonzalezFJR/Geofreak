#!/usr/bin/env python3
"""Build the relief_features.csv dataset from Wikidata.

Three-step pipeline:
  1. SPARQL queries per feature type → item IDs, coords, properties
  2. SPARQL batch queries → country ISO codes per item
  3. MediaWiki API (wbgetentities) → multilingual labels (es, en, fr, it, ru)

Intermediate results are cached in static/data/_cache/ so reruns skip completed steps.

Usage:
    python scripts/build_relief_features.py
    python scripts/build_relief_features.py --force      # ignore cache
    python scripts/build_relief_features.py --skip-labels # reuse cached labels
"""

import argparse
import csv
import json
import os
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "static" / "data"
CACHE_DIR = DATA_DIR / "_cache"
OUTPUT_CSV = DATA_DIR / "relief_features.csv"

CACHE_DIR.mkdir(parents=True, exist_ok=True)

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

SPARQL_URL = "https://query.wikidata.org/sparql"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
UA = "GeoFreak-ReliefBuilder/1.0 (https://github.com/GonzalezFJR/Geofreak)"
LANGUAGES = ["en", "es", "fr", "it", "ru"]

# ── Feature type definitions ────────────────────────────────────────────────
# Each entry: (wikidata_class, sitelinks_min, use_subclass, extra_props, limit)
# extra_props: list of (prop_id, csv_column_name) for OPTIONAL numeric properties
FEATURE_TYPES: dict[str, dict] = {
    "mountain": {
        "qid": "Q8502", "sl_min": 15, "subclass": False,
        "props": [("P2044", "elevation_m")], "limit": 600,
    },
    "volcano": {
        "qid": "Q8072", "sl_min": 5, "subclass": True,
        "props": [("P2044", "elevation_m")], "limit": 300,
    },
    "mountain_range": {
        "qid": "Q46831", "sl_min": 3, "subclass": True,
        "props": [("P2043", "length_km")], "limit": 250,
    },
    "lake": {
        "qid": "Q23397", "sl_min": 10, "subclass": False,
        "props": [("P2046", "area_km2")], "limit": 500,
    },
    "river": {
        "qid": "Q4022", "sl_min": 15, "subclass": False,
        "props": [("P2043", "length_km")], "limit": 500,
    },
    "desert": {
        "qid": "Q8514", "sl_min": 3, "subclass": True,
        "props": [("P2046", "area_km2")], "limit": 100,
    },
    "valley": {
        "qid": "Q39816", "sl_min": 3, "subclass": True,
        "props": [], "limit": 200,
    },
    "canyon": {
        "qid": "Q150784", "sl_min": 3, "subclass": True,
        "props": [("P2043", "length_km")], "limit": 120,
    },
    "plateau": {
        "qid": "Q75520", "sl_min": 3, "subclass": True,
        "props": [("P2046", "area_km2")], "limit": 100,
    },
    "glacier": {
        "qid": "Q35666", "sl_min": 3, "subclass": True,
        "props": [("P2046", "area_km2")], "limit": 180,
    },
    "waterfall": {
        "qid": "Q34038", "sl_min": 3, "subclass": True,
        "props": [("P2044", "elevation_m")], "limit": 180,
    },
    "peninsula": {
        "qid": "Q34763", "sl_min": 3, "subclass": True,
        "props": [("P2046", "area_km2")], "limit": 100,
    },
    "cape": {
        "qid": "Q131681", "sl_min": 3, "subclass": True,
        "props": [], "limit": 100,
    },
    "island": {
        "qid": "Q23442", "sl_min": 5, "subclass": False,
        "props": [("P2046", "area_km2")], "limit": 350,
    },
    "plain": {
        "qid": "Q160091", "sl_min": 3, "subclass": True,
        "props": [("P2046", "area_km2")], "limit": 100,
    },
    "strait": {
        "qid": "Q37901", "sl_min": 3, "subclass": True,
        "props": [("P2043", "length_km")], "limit": 60,
    },
}

# Priority ordering for dedup: more specific type wins
TYPE_PRIORITY = {
    "volcano": 0, "waterfall": 1, "glacier": 2, "canyon": 3,
    "strait": 4, "cape": 5, "peninsula": 6, "island": 7,
    "desert": 8, "plateau": 9, "plain": 10, "valley": 11,
    "mountain_range": 12, "mountain": 13, "lake": 14, "river": 15,
}


# ── HTTP helpers ────────────────────────────────────────────────────────────

def _http_get(url: str, headers: dict | None = None, timeout: int = 60) -> bytes:
    hdrs = {"User-Agent": UA}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    with urllib.request.urlopen(req, context=CTX, timeout=timeout) as resp:
        return resp.read()


def sparql_query(query: str, retries: int = 3) -> list[dict]:
    """Execute a SPARQL query against Wikidata, return list of result bindings."""
    params = urllib.parse.urlencode({"query": query, "format": "json"})
    url = f"{SPARQL_URL}?{params}"
    for attempt in range(retries):
        try:
            data = _http_get(url, {"Accept": "application/sparql-results+json"}, timeout=90)
            result = json.loads(data.decode("utf-8"))
            return result.get("results", {}).get("bindings", [])
        except Exception as e:
            if attempt < retries - 1:
                wait = 5 * (attempt + 1)
                print(f"    Retry {attempt + 1}/{retries} after error: {e} (waiting {wait}s)")
                time.sleep(wait)
            else:
                print(f"    FAILED after {retries} attempts: {e}")
                return []


def parse_coord(point_str: str) -> tuple[float, float] | None:
    """Parse WKT Point(lon lat) → (lat, lon)."""
    m = re.search(r"Point\(([-\d.]+)\s+([-\d.]+)\)", point_str)
    if m:
        return (float(m.group(2)), float(m.group(1)))  # lat, lon
    return None


def get_qid(uri: str) -> str:
    """Extract Q-id from Wikidata entity URI."""
    return uri.rsplit("/", 1)[-1] if "/" in uri else uri


# ── Step 1: SPARQL per feature type ────────────────────────────────────────

def fetch_features_for_type(ftype: str, cfg: dict, force: bool = False) -> list[dict]:
    """Query Wikidata SPARQL for one feature type."""
    cache_file = CACHE_DIR / f"relief_items_{ftype}.json"
    if cache_file.exists() and not force:
        with open(cache_file, "r") as f:
            items = json.load(f)
        print(f"  {ftype}: loaded {len(items)} from cache")
        return items

    qid = cfg["qid"]
    sl_min = cfg["sl_min"]
    subclass = cfg.get("subclass", False)
    extra_props = cfg.get("props", [])
    limit = cfg.get("limit", 500)

    p31_path = "wdt:P31/wdt:P279*" if subclass else "wdt:P31"

    optional_clauses = ""
    select_vars = ""
    for pid, _ in extra_props:
        var = pid.lower()
        optional_clauses += f"\n  OPTIONAL {{ ?item wdt:{pid} ?{var} . }}"
        select_vars += f" (SAMPLE(?{var}) AS ?{var}_val)"

    query = f"""SELECT ?item (SAMPLE(?coord) AS ?coord_val) ?sitelinks{select_vars}
WHERE {{
  ?item {p31_path} wd:{qid} ;
        wdt:P625 ?coord ;
        wikibase:sitelinks ?sitelinks .{optional_clauses}
  FILTER(?sitelinks > {sl_min})
}}
GROUP BY ?item ?sitelinks
ORDER BY DESC(?sitelinks)
LIMIT {limit}"""

    print(f"  {ftype}: querying Wikidata (limit={limit}, sl>{sl_min})...")
    bindings = sparql_query(query)
    print(f"  {ftype}: got {len(bindings)} results")

    items = []
    for b in bindings:
        coord = parse_coord(b.get("coord_val", {}).get("value", ""))
        if not coord:
            continue
        item = {
            "wikidata_id": get_qid(b["item"]["value"]),
            "type": ftype,
            "lat": round(coord[0], 5),
            "lon": round(coord[1], 5),
            "sitelinks": int(b.get("sitelinks", {}).get("value", 0)),
        }
        for pid, col in extra_props:
            var = f"{pid.lower()}_val"
            val = b.get(var, {}).get("value")
            if val is not None:
                try:
                    item[col] = round(float(val), 2)
                except (ValueError, TypeError):
                    pass
        items.append(item)

    with open(cache_file, "w") as f:
        json.dump(items, f)

    return items


# ── Step 2: Country codes ──────────────────────────────────────────────────

def fetch_country_codes(all_items: list[dict], force: bool = False) -> dict[str, str]:
    """Fetch country ISO codes for all items, in batches."""
    cache_file = CACHE_DIR / "relief_countries.json"
    if cache_file.exists() and not force:
        with open(cache_file, "r") as f:
            data = json.load(f)
        print(f"  Countries: loaded {len(data)} from cache")
        return data

    qids = list({it["wikidata_id"] for it in all_items})
    print(f"  Countries: fetching for {len(qids)} items...")

    result: dict[str, str] = {}
    batch_size = 150

    for i in range(0, len(qids), batch_size):
        batch = qids[i : i + batch_size]
        values = " ".join(f"wd:{q}" for q in batch)
        query = f"""SELECT ?item (GROUP_CONCAT(DISTINCT ?cc; SEPARATOR=",") AS ?countries)
WHERE {{
  VALUES ?item {{ {values} }}
  ?item wdt:P17 ?country .
  ?country wdt:P298 ?cc .
}}
GROUP BY ?item"""

        bindings = sparql_query(query)
        for b in bindings:
            qid = get_qid(b["item"]["value"])
            codes = b.get("countries", {}).get("value", "")
            if codes:
                result[qid] = codes

        pct = min(100, round((i + len(batch)) / len(qids) * 100))
        print(f"    batch {i // batch_size + 1}: {pct}% done ({len(result)} codes so far)")
        time.sleep(1.5)

    with open(cache_file, "w") as f:
        json.dump(result, f)

    print(f"  Countries: got codes for {len(result)} items")
    return result


# ── Step 3: Multilingual labels ────────────────────────────────────────────

def fetch_labels(all_items: list[dict], force: bool = False) -> dict[str, dict]:
    """Fetch labels in all languages via MediaWiki API."""
    cache_file = CACHE_DIR / "relief_labels.json"
    if cache_file.exists() and not force:
        with open(cache_file, "r") as f:
            data = json.load(f)
        print(f"  Labels: loaded {len(data)} from cache")
        return data

    qids = list({it["wikidata_id"] for it in all_items})
    print(f"  Labels: fetching for {len(qids)} items...")

    result: dict[str, dict] = {}
    batch_size = 50
    langs = "|".join(LANGUAGES)

    for i in range(0, len(qids), batch_size):
        batch = qids[i : i + batch_size]
        ids_str = "|".join(batch)
        params = urllib.parse.urlencode({
            "action": "wbgetentities",
            "ids": ids_str,
            "props": "labels",
            "languages": langs,
            "format": "json",
        })
        url = f"{WIKIDATA_API}?{params}"

        try:
            data = json.loads(_http_get(url, timeout=30).decode("utf-8"))
            entities = data.get("entities", {})
            for qid, ent in entities.items():
                labels = {}
                for lang in LANGUAGES:
                    lbl = ent.get("labels", {}).get(lang, {}).get("value", "")
                    if lbl:
                        labels[f"name_{lang}"] = lbl
                if labels:
                    result[qid] = labels
        except Exception as e:
            print(f"    ERROR fetching labels batch {i // batch_size + 1}: {e}")

        if (i // batch_size) % 10 == 9:
            pct = min(100, round((i + len(batch)) / len(qids) * 100))
            print(f"    {pct}% done ({len(result)} labels so far)")

        time.sleep(0.5)

    with open(cache_file, "w") as f:
        json.dump(result, f)

    print(f"  Labels: got labels for {len(result)} items")
    return result


# ── Country name lookup ────────────────────────────────────────────────────

def build_country_name_map() -> dict[str, str]:
    """Build ISO3 → English name map from countries.csv if available."""
    csv_path = DATA_DIR / "countries.csv"
    mapping: dict[str, str] = {}
    if csv_path.exists():
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                iso3 = row.get("iso_a3", "")
                name = row.get("name", "")
                if iso3 and name:
                    mapping[iso3] = name
    return mapping


# ── Assembly ───────────────────────────────────────────────────────────────

def assemble_csv(
    all_items: list[dict],
    countries: dict[str, str],
    labels: dict[str, dict],
    country_names: dict[str, str],
) -> list[dict]:
    """Merge all data sources, deduplicate, and produce final rows."""
    # Deduplicate by wikidata_id: keep the type with highest priority (lowest number)
    seen: dict[str, dict] = {}
    for item in all_items:
        qid = item["wikidata_id"]
        if qid in seen:
            existing_prio = TYPE_PRIORITY.get(seen[qid]["type"], 99)
            new_prio = TYPE_PRIORITY.get(item["type"], 99)
            if new_prio < existing_prio:
                # Merge properties from old into new (keep extra data)
                for k, v in seen[qid].items():
                    if k not in item or item[k] is None:
                        item[k] = v
                seen[qid] = item
            else:
                # Merge properties from new into existing
                for k, v in item.items():
                    if k not in seen[qid] or seen[qid][k] is None:
                        seen[qid][k] = v
        else:
            seen[qid] = item

    rows = []
    for qid, item in seen.items():
        lbl = labels.get(qid, {})
        name_en = lbl.get("name_en", "")
        if not name_en:
            continue  # Skip items without at least an English name

        cc = countries.get(qid, "")
        cn = ", ".join(country_names.get(c.strip(), c.strip()) for c in cc.split(",") if c.strip())

        rows.append({
            "wikidata_id": qid,
            "name": name_en,
            "name_es": lbl.get("name_es", name_en),
            "name_en": name_en,
            "name_fr": lbl.get("name_fr", name_en),
            "name_it": lbl.get("name_it", name_en),
            "name_ru": lbl.get("name_ru", name_en),
            "type": item["type"],
            "country_codes": cc,
            "country_names_en": cn,
            "lat": item["lat"],
            "lon": item["lon"],
            "elevation_m": item.get("elevation_m", ""),
            "length_km": item.get("length_km", ""),
            "area_km2": item.get("area_km2", ""),
            "sitelinks": item.get("sitelinks", 0),
        })

    # Sort by type priority, then by sitelinks descending
    rows.sort(key=lambda r: (TYPE_PRIORITY.get(r["type"], 99), -r["sitelinks"]))

    # Assign sequential IDs
    for i, row in enumerate(rows, 1):
        row["id"] = i

    return rows


def write_csv(rows: list[dict]) -> None:
    """Write the final CSV."""
    fieldnames = [
        "id", "wikidata_id", "name", "name_es", "name_en", "name_fr", "name_it",
        "name_ru", "type", "country_codes", "country_names_en", "lat", "lon",
        "elevation_m", "length_km", "area_km2", "sitelinks",
    ]
    with open(OUTPUT_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nWrote {len(rows)} features to {OUTPUT_CSV}")


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Build relief features CSV from Wikidata")
    parser.add_argument("--force", action="store_true", help="Ignore cache, re-fetch everything")
    parser.add_argument("--skip-labels", action="store_true", help="Skip label fetching (use cache)")
    args = parser.parse_args()

    print("=" * 60)
    print("Building relief features dataset from Wikidata")
    print("=" * 60)

    # Step 1: Fetch features per type
    print("\n--- Step 1: Fetching features by type ---")
    all_items: list[dict] = []
    for ftype, cfg in FEATURE_TYPES.items():
        items = fetch_features_for_type(ftype, cfg, force=args.force)
        all_items.extend(items)
        time.sleep(2)  # Rate limiting between SPARQL queries

    print(f"\nTotal raw items: {len(all_items)}")

    # Step 2: Fetch country codes
    print("\n--- Step 2: Fetching country codes ---")
    countries = fetch_country_codes(all_items, force=args.force)

    # Step 3: Fetch multilingual labels
    print("\n--- Step 3: Fetching multilingual labels ---")
    if args.skip_labels:
        cache_file = CACHE_DIR / "relief_labels.json"
        if cache_file.exists():
            with open(cache_file, "r") as f:
                labels_data = json.load(f)
            print(f"  Labels: loaded {len(labels_data)} from cache (--skip-labels)")
        else:
            print("  No cached labels found, fetching...")
            labels_data = fetch_labels(all_items, force=args.force)
    else:
        labels_data = fetch_labels(all_items, force=args.force)

    # Build country name map
    country_names = build_country_name_map()

    # Assemble final CSV
    print("\n--- Assembling CSV ---")
    rows = assemble_csv(all_items, countries, labels_data, country_names)

    # Stats
    type_counts: dict[str, int] = {}
    for r in rows:
        type_counts[r["type"]] = type_counts.get(r["type"], 0) + 1
    print("\nFeatures per type:")
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {t}: {c}")

    # Write CSV
    write_csv(rows)


if __name__ == "__main__":
    main()
