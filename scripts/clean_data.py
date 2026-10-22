"""Normalize raw per-source records (no merging here).

Reads data/raw/<source_type>_<snapshot date>.json, writes data/processed/records_normalized.json.
Unknown / invalid values become empty strings; every issue is logged to
data/processed/cleaning_issues.json so nothing is silently dropped or guessed.
Records whose source did not answer HTTP 200 are excluded (listed in excluded_records.json):
every row in the final dataset must be traceable to a page that was actually read.
"""
import sys

from common import (CATEGORIES, PLATFORMS, PROCESSED, RAW, clean_text, ensure_dirs, join_multi, norm_category,
                    norm_date, norm_languages, norm_license, norm_license_model, norm_year, read_json,
                    snapshot_date, split_multi, valid_url, write_json)

SOURCE_TYPES = ("published_list", "curated_list", "wikipedia_article", "vendor_origin", "vendor_site",
                "public_repository", "repository_search", "documentation", "github_topics")


def normalize(rec, issues):
    out = {}
    name = clean_text(rec.get("tool_name"))
    out["tool_name"] = name
    out["vendor_maintainer"] = clean_text(rec.get("vendor_maintainer"))[:80]
    out["country_region"] = clean_text(rec.get("country_region"))

    cat = norm_category(rec.get("category"))
    if clean_text(rec.get("category")) and not cat:
        issues.append({"tool": name, "issue": "category outside vocabulary", "value": rec.get("category")})
    out["category"] = cat
    out["additional_categories"] = join_multi(c for c in split_multi(rec.get("additional_categories"))
                                              if c in CATEGORIES and c != cat)

    lm = norm_license_model(rec.get("license_model"))
    if clean_text(rec.get("license_model")) and not lm:
        issues.append({"tool": name, "issue": "unrecognised license_model", "value": rec.get("license_model")})
    out["license_model"] = lm
    out["license"] = norm_license(rec.get("license"))

    for f in ("website_url", "repository_url", "wikipedia_url", "source_url"):
        v = valid_url(rec.get(f))
        if clean_text(rec.get(f)) and not v:
            issues.append({"tool": name, "issue": "invalid URL in " + f, "value": rec.get(f)})
        out[f] = v

    out["first_release_year"] = norm_year(rec.get("first_release_year"))
    out["latest_version"] = clean_text(rec.get("latest_version"))
    out["latest_release_date"] = norm_date(rec.get("latest_release_date"))
    out["latest_release_year"] = norm_year(rec.get("latest_release_year")) or out["latest_release_date"][:4]
    out["supported_platforms"] = join_multi(p for p in split_multi(rec.get("supported_platforms")) if p in PLATFORMS)
    out["languages_formats"] = norm_languages(rec.get("languages_formats"))
    out["source_type"] = clean_text(rec.get("source_type"))
    out["date_collected"] = norm_date(rec.get("date_collected"))
    out["fetch_status"] = str(rec.get("fetch_status", ""))
    if (out["first_release_year"] and out["latest_release_year"]
            and out["first_release_year"] > out["latest_release_year"]):
        issues.append({"tool": name, "issue": "first release after latest release; first_release_year dropped",
                       "value": "%s > %s" % (out["first_release_year"], out["latest_release_year"])})
        out["first_release_year"] = ""
    return out


def main():
    ensure_dirs()
    date = snapshot_date()
    files = [RAW / ("%s_%s.json" % (s, date)) for s in SOURCE_TYPES]
    files = [f for f in files if f.exists()]
    if not files:
        sys.exit("No raw files for snapshot date %s in %s. Run the collectors first "
                 "(or set EDA_SNAPSHOT_DATE to an existing snapshot)." % (date, RAW))
    issues, records, excluded = [], [], []
    for f in files:
        for rec in read_json(f, []):
            n = normalize(rec, issues)
            if not n["tool_name"]:
                issues.append({"tool": "", "issue": "record without tool_name dropped", "file": f.name})
            elif n["fetch_status"] != "200" or not n["source_url"] or not n["date_collected"]:
                excluded.append({"tool": n["tool_name"], "source_url": n["source_url"],
                                 "fetch_status": n["fetch_status"], "reason": "source not verified"})
            else:
                records.append(n)
    write_json(PROCESSED / "records_normalized.json", records)
    write_json(PROCESSED / "cleaning_issues.json", issues)
    write_json(PROCESSED / "excluded_records.json", excluded)
    print("cleaned %d records from %d files (snapshot %s); %d excluded; %d issues logged"
          % (len(records), len(files), date, len(excluded), len(issues)))


if __name__ == "__main__":
    main()
