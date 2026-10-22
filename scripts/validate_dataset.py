"""Validate the cleaned dataset: schema, one row per tool, traceable provenance, controlled
vocabularies, and the problem statement's coverage requirements. Exits non-zero on any error."""
import csv
import sys
from collections import Counter

from common import (CATEGORIES, FINAL_FIELDS, PCB_NOT_IC_STAGES, PLATFORMS, PROCESSED, region_of, split_multi,
                    valid_url)

REQUIRED_REGIONS = ("North America", "Europe", "Asia")


def main():
    with open(PROCESSED / "eda_tools_clean.csv", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        header, rows = reader.fieldnames, list(reader)
    with open(PROCESSED / "provenance.csv", encoding="utf-8", newline="") as f:
        prov = list(csv.DictReader(f))
    prov_ids = {r["tool_id"] for r in prov}
    errors, warnings, seen = [], [], set()
    if header != FINAL_FIELDS:
        errors.append("column set differs from schema")
    for i, r in enumerate(rows, start=2):
        where = "row %d (%s)" % (i, r["tool_id"])
        if r["tool_id"] in seen:
            errors.append(where + ": duplicate tool_id")
        seen.add(r["tool_id"])
        if not r["tool_name"]:
            errors.append(where + ": missing tool_name")
        if not valid_url(r["source_url"]):
            errors.append(where + ": missing/invalid source_url")
        if not r["date_collected"]:
            errors.append(where + ": missing date_collected")
        if r["tool_id"] not in prov_ids:
            errors.append(where + ": no provenance rows")
        if r["source_verified"] != "true":
            errors.append(where + ": a contributing source was not verified")
        if r["category"] and r["category"] not in CATEGORIES:
            errors.append(where + ": category outside vocabulary")
        if any(c not in CATEGORIES for c in split_multi(r["additional_categories"])):
            errors.append(where + ": additional category outside vocabulary")
        if r["license_model"] not in ("", "commercial", "open-source", "freeware"):
            errors.append(where + ": licence model outside vocabulary")
        if any(p not in PLATFORMS for p in split_multi(r["supported_platforms"])):
            errors.append(where + ": platform outside vocabulary")
        if bool(r["vendor_maintainer"]) != bool(r["vendor_canonical"]):
            errors.append(where + ": vendor_canonical must be filled exactly when vendor_maintainer is")
        if r["category"] == "pcb-design" and PCB_NOT_IC_STAGES & set(split_multi(r["additional_categories"])):
            errors.append(where + ": PCB tool carries an IC-only secondary category")
        if r["region"] != region_of(r["country_region"]):
            errors.append(where + ": region does not match country")
        if r["first_release_year"] and r["latest_release_year"] and r["first_release_year"] > r["latest_release_year"]:
            errors.append(where + ": first release after latest release")
        if not r["category"]:
            warnings.append(where + ": category not found in any source")
    for p in prov:
        if not valid_url(p["source_url"]) or p["fetch_status"] != "200":
            errors.append("provenance %s: unverified source %s" % (p["tool_id"], p["source_url"]))

    # coverage requirements from the problem statement (reported; failures are warnings, not errors,
    # because coverage depends on what the live sources contain on the collection day)
    models = Counter(r["license_model"] for r in rows)
    regions = Counter(r["region"] for r in rows if r["region"])
    cats = Counter(c for r in rows for c in [r["category"]] + split_multi(r["additional_categories"]) if c)
    print("coverage: licence models %s" % dict(models))
    print("coverage: regions %s" % dict(regions))
    print("coverage: categories %s" % {c: cats.get(c, 0) for c in CATEGORIES})
    if not (models["commercial"] and models["open-source"]):
        warnings.append("coverage: need both commercial and open-source tools")
    for reg in REQUIRED_REGIONS:
        if not regions.get(reg):
            warnings.append("coverage: no tool with a documented origin in " + reg)
    for c in CATEGORIES:
        if not cats.get(c):
            warnings.append("coverage: no tool in category " + c)

    print("%d rows, %d errors, %d warnings" % (len(rows), len(errors), len(warnings)))
    for m in errors[:100]:
        print("ERROR:", m)
    for m in [w for w in warnings if w.startswith("coverage")] + [w for w in warnings if not w.startswith("coverage")][:15]:
        print("WARN:", m)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
