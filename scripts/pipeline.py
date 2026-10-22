"""Run the whole project in order. Launch it through Crucible:

    igny run script ./scripts/pipeline.py                       # rebuild from the committed snapshot
    igny run script ./scripts/pipeline.py -- --collect          # fresh collection from live sources
    EDA_COLLECT=1 igny run script ./scripts/pipeline.py         # same, if igny/your shell rejects '-- --collect'
                                                                # (PowerShell: $env:EDA_COLLECT = "1")
    igny run script ./scripts/pipeline.py -- --snapshot 2026-10-15

Every step is started with the same Crucible interpreter that igny resolved (sys.executable) and with
'-s', so the user's personal site-packages can never leak in. The snapshot date is fixed once at the
start, so all steps of one run read and write the same dated files even across midnight.
"""
import argparse
import datetime
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE.parent / "data" / "raw"
COLLECT = ["collect_published_lists.py", "collect_curated_lists.py", "collect_wikipedia_articles.py",
           "collect_vendor_sites.py", "collect_public_repositories.py", "collect_github_topics.py",
           "collect_github_search.py", "collect_documentation.py", "collect_vendor_origin.py"]
PROCESS = ["clean_data.py", "deduplicate_data.py", "validate_dataset.py", "run_analysis.py", "make_dashboard.py"]
def latest_snapshot():
    dates = sorted(p.stem.rsplit("_", 1)[-1] for p in RAW.glob("published_list_*.json"))
    return dates[-1] if dates else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--collect", action="store_true", help="collect fresh data from the live sources first")
    ap.add_argument("--snapshot", help="snapshot date to process (default: newest in data/raw)")
    a = ap.parse_args()
    # some igny/shell combinations do not pass '-- --collect' through, so EDA_COLLECT=1 does the same thing
    a.collect = a.collect or os.environ.get("EDA_COLLECT", "").strip().lower() in ("1", "true", "yes")
    date =datetime.date.today().isoformat() if a.collect else (a.snapshot or latest_snapshot())
    if not date:
        sys.exit("No snapshot in data/raw; run with --collect")
    env = dict(os.environ, EDA_SNAPSHOT_DATE=date, PYTHONNOUSERSITE="1")
    # fresh collection: fingerprint the new raw files; offline rebuild: first prove the raw files are the committed ones
    steps = (["check_environment.py"] + (COLLECT + ["snapshot_manifest.py"] if a.collect
                                         else [("snapshot_manifest.py", "--verify")]) + PROCESS)
    steps = [(s,) if isinstance(s, str) else s for s in steps]
    print("snapshot %s | steps: %s" % (date, ", ".join(s[0] for s in steps)))
    for s, *extra in steps:
        print("\n=== %s" % s, flush=True)
        r = subprocess.run([sys.executable, "-s", str(HERE / s)] + extra, env=env)
        if r.returncode != 0:
            sys.exit("step %s failed (exit %d)" % (s, r.returncode))
    print("\npipeline finished for snapshot %s" % date)


if __name__ == "__main__":
    main()
