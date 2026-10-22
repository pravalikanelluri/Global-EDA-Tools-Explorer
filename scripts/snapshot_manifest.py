"""Fingerprint the raw snapshot so 'the committed snapshot' is a checkable fact, not a promise.

    igny run script ./scripts/snapshot_manifest.py            # write data/raw/SNAPSHOT_MANIFEST.json
    igny run script ./scripts/snapshot_manifest.py -- --verify   # exit 1 if a raw file differs from the manifest

For every data/raw/<source>_<snapshot date>.json the manifest records the SHA-256 of the content (line endings
normalised, so a Windows checkout with CRLF gives the same hash), the number of records, and the earliest and
latest `date_collected` inside the file. The latter makes a partial refresh visible: a file named _2026-10-15 that
holds records collected on 2026-10-19 says so. The collection log is excluded (it is append-only by design).
The manifest contains no timestamps, so the same raw files always produce the same manifest.
"""
import hashlib
import sys

from common import RAW, ensure_dirs, read_json, snapshot_date, write_json

MANIFEST = RAW / "SNAPSHOT_MANIFEST.json"


def fingerprint(path):
    data = path.read_bytes().replace(b"\r\n", b"\n")
    recs = read_json(path, []) or []
    dates = sorted(r.get("date_collected", "") for r in recs if isinstance(r, dict) and r.get("date_collected"))
    return {"sha256": hashlib.sha256(data).hexdigest(), "records": len(recs),
            "date_collected_min": dates[0] if dates else "", "date_collected_max": dates[-1] if dates else ""}


def current(date):
    return {p.name: fingerprint(p) for p in sorted(RAW.glob("*_%s.json" % date))}


def main():
    ensure_dirs()
    date = snapshot_date()
    files = current(date)
    if not files:
        sys.exit("No raw files for snapshot date %s in %s" % (date, RAW))
    if "--verify" in sys.argv[1:]:
        recorded = read_json(MANIFEST)
        if not recorded:
            print("snapshot manifest: none recorded yet (run without --verify to create it)")
            return
        if recorded.get("snapshot_date") != date:
            print("snapshot manifest: recorded for %s, processing %s - skipped" % (recorded.get("snapshot_date"), date))
            return
        problems = []
        for name, fp in recorded["files"].items():
            now = files.get(name)
            if now is None:
                problems.append("missing: " + name)
            elif now["sha256"] != fp["sha256"]:
                problems.append("changed: " + name)
        problems += ["unlisted: " + n for n in files if n not in recorded["files"]]
        if problems:
            sys.exit("snapshot manifest MISMATCH (%s) - the raw data is not the committed snapshot:\n  %s\n"
                     "If you collected or refreshed data on purpose, record it with\n"
                     "  igny run script ./scripts/snapshot_manifest.py\n"
                     "and commit the raw files together with data/raw/SNAPSHOT_MANIFEST.json."
                     % (date, "\n  ".join(problems)))
        print("snapshot manifest OK: %d raw files match (snapshot %s)" % (len(files), date))
        return
    write_json(MANIFEST, {"snapshot_date": date, "files": files})
    print("snapshot manifest written: %d files -> %s" % (len(files), MANIFEST))
    mixed = {n: (f["date_collected_min"], f["date_collected_max"]) for n, f in files.items()
             if f["date_collected_min"] != f["date_collected_max"]}
    for n, (lo, hi) in mixed.items():
        print("note: %s holds records collected on several days (%s .. %s)" % (n, lo, hi))


if __name__ == "__main__":
    main()
