#!/usr/bin/env python3
"""Fetch real-person 八字 + verified life events from Wikidata (no volunteers).

Expands the real-person pool beyond MingLi(32)/celebrity50(50). Wikidata has
structured, public, verifiable data: birth date/time (P569), sex (P21),
death (P570), spouse + marriage start (P26/P580), occupation (P106), children.

Honest limitation: most Wikidata births are DATE-only (time zeroed to T00:00).
Real birth times are rare (some royals/politicians). We flag `has_time`:
  - has_time=True  → full 4-pillar 八字, directly usable.
  - has_time=False → 3-pillar (year/month/day), hour unknown → event/year
                     validation only, NOT full 八字.

Output: JSONL of records in a celebrity50-compatible shape, consumed by
validate_mingli/validate_past after conversion.

Usage::
    python benchmarks/baziqa/fetch_celebrities.py --limit 300 \
        --out benchmarks/baziqa/data/wikidata_celebs.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

SPARQL_URL = "https://query.wikidata.org/sparql"
USER_AGENT = "bazi-accuracy-research/1.0 (local research)"

# Humans born 1900+, with a birth date, sex, an en OR zh Wikipedia article
# (notability filter), and at least a death date or spouse (so we have events).
QUERY = """
SELECT ?item ?itemLabel ?birth ?sexLabel ?death ?occupLabel
       (GROUP_CONCAT(DISTINCT ?spouseLabel; separator="|") AS ?spouses)
       (GROUP_CONCAT(DISTINCT ?marrStart; separator="|") AS ?marrStarts)
WHERE {
  ?item wdt:P31 wd:Q5;
        wdt:P569 ?birth;
        wdt:P21 ?sex.
  FILTER(YEAR(?birth) >= 1920 AND YEAR(?birth) <= 2005)
  { ?item wdt:P570 ?death. } UNION { ?item wdt:P26 ?_sp. }
  OPTIONAL { ?item wdt:P570 ?death. }
  OPTIONAL { ?item wdt:P106 ?occup. }
  OPTIONAL { ?item wdt:P26 ?spouse. }
  OPTIONAL { ?item p:P26 ?ms. ?ms ps:P26 ?spouse; pq:P580 ?marrStart. }
  ?article schema:about ?item.
  { ?article schema:isPartOf <https://en.wikipedia.org/>. }
  UNION
  { ?article schema:isPartOf <https://zh.wikipedia.org/>. }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "zh,en". }
}
GROUP BY ?item ?itemLabel ?birth ?sexLabel ?death ?occupLabel
LIMIT %d
"""


def _run_sparql(limit: int) -> list:
    q = QUERY % limit
    url = SPARQL_URL + "?query=" + urllib.parse.quote(q) + "&format=json"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept": "application/sparql-results+json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.load(resp)
    return data.get("results", {}).get("bindings", [])


def _parse_birth(raw: str):
    """Parse Wikidata datetime '1958-03-14T12:00:00Z' → (y,m,d,h,mi,has_time)."""
    try:
        datepart, timepart = raw.split("T")
        y, m, d = map(int, datepart.split("-")[:3])
        hh, mi = 0, 0
        has_time = False
        if "T" in raw and "Z" in timepart:
            t = timepart.replace("Z", "")
            parts = t.split(":")
            hh = int(parts[0])
            mi = int(parts[1]) if len(parts) > 1 else 0
            # Wikidata stores date-only as T00:00:00Z; non-zero hour = real birth time
            has_time = (hh != 0 or mi != 0)
        return y, m, d, hh, mi, has_time
    except Exception:
        return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--out", default="benchmarks/baziqa/data/wikidata_celebs.jsonl")
    args = ap.parse_args()

    print(f"Querying Wikidata (limit {args.limit})…", file=sys.stderr)
    rows = _run_sparql(args.limit)
    print(f"Got {len(rows)} rows. Parsing…", file=sys.stderr)

    recs = []
    n_full = n_3p = 0
    for r in rows:
        b = _parse_birth(r.get("birth", {}).get("value", ""))
        if not b:
            continue
        y, m, d, hh, mi, has_time = b
        name = r.get("itemLabel", {}).get("value", "")
        gender = "male" if r.get("sexLabel", {}).get("value") == "male" else "female"
        death = r.get("death", {}).get("value", "")[:4]
        occup = r.get("occupLabel", {}).get("value", "")
        spouses = (r.get("spouses", {}).get("value") or "").split("|")
        marrs = (r.get("marrStarts", {}).get("value") or "").split("|")
        events = []
        for ms in marrs:
            if ms[:4].isdigit():
                events.append({"year": int(ms[:4]), "event": f"与{spouses[0] if spouses else ''}结婚"})
        if death.isdigit():
            events.append({"year": int(death), "event": "去世"})
        rec = {
            "name": name,
            "source": "wikidata",
            "profile": {"gender": gender,
                        "birth": {"year": y, "month": m, "day": d, "hour": hh, "minute": mi},
                        "has_time": has_time,
                        "occupation": occup, "death_year": int(death) if death.isdigit() else None},
            "known_facts": {"events": events,
                            "career": [occup] if occup else []},
        }
        recs.append(rec)
        if has_time:
            n_full += 1
        else:
            n_3p += 1

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\nWrote {len(recs)} → {args.out}", file=sys.stderr)
    print(f"  full 4-pillar (has birth time): {n_full}", file=sys.stderr)
    print(f"  3-pillar only (date, no time) : {n_3p}", file=sys.stderr)
    if recs:
        print(f"\nSample: {json.dumps(recs[0], ensure_ascii=False)[:300]}", file=sys.stderr)


if __name__ == "__main__":
    main()
