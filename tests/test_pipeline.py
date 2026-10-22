"""Offline end-to-end test of clean -> dedup -> validate -> analysis on a synthetic fixture.

Run through Crucible:  igny run script ./tests/test_pipeline.py
The fixture uses made-up tools ("Example ...") and a temporary project root, so it never touches real
data and needs no network. It checks: unverified sources are excluded, records merge across sources by
repository / name, an empty-vendor record cannot bridge two different vendors, conflicting vendors go to
review, country comes from the vendor_origin record, the release triple stays together, provenance is kept.
"""
import csv
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
FIX = HERE / "fixtures"


def run(script, env):
    r = subprocess.run([sys.executable, "-s", str(SCRIPTS / script)], env=env, capture_output=True, text=True)
    assert r.returncode == 0, "%s failed:\n%s\n%s" % (script, r.stdout, r.stderr)
    return r.stdout


def unit_checks():
    sys.path.insert(0, str(SCRIPTS))
    from common import (CATEGORIES, categorize, country_from_text, norm_category, norm_date, norm_platforms,
                        license_model_from)
    for c in CATEGORIES:
        assert norm_category(c) == c, "vocabulary term not accepted: " + c
    assert country_from_text("Sunnyvale, California, U.S.") == "United States"
    assert country_from_text("Yokohama, Japan") == "Japan"
    assert country_from_text("Wilsonville, Oregon") == "United States"
    assert norm_date("10.0.6 / 29 August 2025; 46 days ago") == "2025-08-29"
    assert norm_platforms("Linux, macOS, Microsoft Windows") == "Linux; Windows; macOS"
    assert license_model_from("GPL-3.0-or-later") == "open-source"
    assert license_model_from("Proprietary") == "commercial"
    assert categorize("PrimeTime Static Timing Analysis | Synopsys")[0] == "timing-signoff"
    assert categorize("Comparison of proprietary software for PCB design")[0] == "pcb-design"
    assert categorize("Design Compiler offers best-in-class RTL synthesis ... high test coverage",
                      by_position=True) == ["synthesis", "verification"]
    from collect_vendor_sites import definition_sentence, vendor_from
    assert vendor_from({"site_name": "", "title": "PRIMARIUS - NanoSpice"}, "Primarius NanoSpice") == "PRIMARIUS"
    assert vendor_from({"site_name": "", "title": "Empyrean Aether™ – Layout Design_Product Portfolio_Empyrean "
                        "Technology Co., Ltd"}, "Empyrean Aether") == "Empyrean Technology Co., Ltd"
    assert vendor_from({"site_name": "", "title": "PrimeTime Static Timing Analysis | Synopsys"},
                       "Synopsys PrimeTime") == "Synopsys"
    assert categorize(definition_sentence("NanoSpice X; NanoSpice is a new generation of parallel SPICE simulator. "
                                          "Designed for", "Primarius NanoSpice"))[0] == "analog-mixed-signal"
    from collect_public_repositories import readme_summary
    assert readme_summary("# Parallax Static Timing Analyzer\n\n[![b](x)](y)\nOpenSTA is a gate level static timing "
                          "verifier.\nAs a stand-alone\n\n* Verilog netlist") == \
        "Parallax Static Timing Analyzer. OpenSTA is a gate level static timing verifier. As a stand-alone"
    from collect_github_topics import repo_to_record
    base = {"name": "example-router", "full_name": "example-lab/example-router", "fork": False, "archived": False,
            "description": "Open-source place and route tool for ASIC and FPGA netlists", "topics": ["eda", "asic"],
            "license": {"spdx_id": "Apache-2.0"}, "owner": {"login": "example-lab"}, "stargazers_count": 40,
            "homepage": "https://example.lab/router", "html_url": "https://github.com/example-lab/example-router"}
    rec, why = repo_to_record(base)
    assert why is None and rec["category"] == "place-and-route" and rec["license_model"] == "open-source", (rec, why)
    assert rec["source_type"] == "github_topics" and rec["source_url"].endswith("/repos/example-lab/example-router")
    assert rec["vendor_maintainer"] == "example-lab" and rec["first_release_year"] == "" and rec["country_region"] == ""
    skip = lambda **kw: repo_to_record(dict(base, **kw))[1]
    assert skip(fork=True) == "fork" and skip(archived=True) == "archived"
    assert "anchor" in skip(description="Speech synthesis engine", topics=[], name="voice")
    assert "anchor" in skip(description="NASA SPICE toolkit for ancillary space data", topics=["spice"], name="naif")
    assert repo_to_record(dict(base, name="xyce-lite", description="Parallel circuit simulator, SPICE compatible",
                               topics=["spice"]))[1] is None
    assert "not a tool" in skip(description="Verilog course notes for ASIC design", topics=[])
    assert "not a tool" in skip(description="A RISC-V soft core in Verilog for FPGA", topics=[])
    assert "tool-like" in skip(description="My FPGA project for a school lab", topics=["fpga"], name="lab")
    assert "category" in skip(description="ASIC toolkit for hobbyists", topics=[], name="hobby")
    assert skip(description="", topics=[]) == "no description or topics"
    assert repo_to_record(dict(base, license={"spdx_id": "NOASSERTION"}))[0]["license"] == ""
    from deduplicate_data import apply_pcb_rule, canonical_vendors, vendors_compatible
    canon = canonical_vendors(["Cadence", "Cadence", "Cadence Design Systems", "Altium",
                               "Altium (included in Altium Develop and Altium Agile)", "YosysHQ", "", "Zuken"])
    assert canon("Cadence Design Systems") == "Cadence" and canon("Cadence") == "Cadence"
    assert canon("Altium (included in Altium Develop and Altium Agile)") == "Altium"
    assert canon("YosysHQ") == "YosysHQ" and canon("") == "" and canon("Unknown Co") == ""
    assert apply_pcb_rule("pcb-design", "analog-mixed-signal; layout-physical-verification; simulation") == \
        ("analog-mixed-signal; simulation", ["layout-physical-verification"])
    assert apply_pcb_rule("pcb-design", "place-and-route; timing-signoff")[0] == ""
    assert apply_pcb_rule("synthesis", "place-and-route") == ("place-and-route", [])  # only PCB-primary tools
    assert vendors_compatible("Cadence", "Cadence Design Systems")
    assert vendors_compatible("Autodesk (previously CadSoft Computer)", "Autodesk / CadSoft Computer (discontinued)")
    assert not vendors_compatible("National Instruments", "National Semiconductor")


def main():
    unit_checks()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        raw = root / "data" / "raw"
        raw.mkdir(parents=True)
        (raw / "published_list_2026-01-01.json").write_text((FIX / "raw_sample.json").read_text())
        (raw / "public_repository_2026-01-01.json").write_text((FIX / "raw_repo_sample.json").read_text())
        (raw / "vendor_origin_2026-01-01.json").write_text((FIX / "raw_origin_sample.json").read_text())
        (raw / "github_topics_2026-01-01.json").write_text((FIX / "raw_topics_sample.json").read_text())
        env = dict(os.environ, EDA_PROJECT_ROOT=str(root), EDA_SNAPSHOT_DATE="2026-01-01", PYTHONNOUSERSITE="1")
        # raw snapshot fingerprint: write, verify, then tamper with a file and expect a failure
        run("snapshot_manifest.py", env)
        assert "manifest OK" in subprocess.run([sys.executable, "-s", str(SCRIPTS / "snapshot_manifest.py"),
                                                "--verify"], env=env, capture_output=True, text=True).stdout
        manifest = json.load(open(raw / "SNAPSHOT_MANIFEST.json"))
        assert sorted(manifest["files"]) == ["github_topics_2026-01-01.json", "public_repository_2026-01-01.json",
                                             "published_list_2026-01-01.json", "vendor_origin_2026-01-01.json"], manifest
        # CRLF checkout (Windows autocrlf) must not change the fingerprint
        p = raw / "published_list_2026-01-01.json"
        p.write_bytes(p.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        assert subprocess.run([sys.executable, "-s", str(SCRIPTS / "snapshot_manifest.py"), "--verify"], env=env,
                              capture_output=True).returncode == 0
        p.write_text(p.read_text().replace("Example Forge", "Example Forgery"))
        bad = subprocess.run([sys.executable, "-s", str(SCRIPTS / "snapshot_manifest.py"), "--verify"], env=env,
                             capture_output=True, text=True)
        assert bad.returncode != 0 and "published_list_2026-01-01.json" in (bad.stdout + bad.stderr), bad
        p.write_text(p.read_text().replace("Example Forgery", "Example Forge"))

        run("clean_data.py", env)
        run("deduplicate_data.py", env)
        run("validate_dataset.py", env)
        run("run_analysis.py", env)

        proc = root / "data" / "processed"
        rows = list(csv.DictReader(open(proc / "eda_tools_clean.csv", encoding="utf-8")))
        ids = sorted(r["tool_id"] for r in rows)
        assert ids == ["example-forge", "example-forge-2", "example-router", "example-sim"], ids  # 404 'Sim Pro' excluded
        sim = next(r for r in rows if r["tool_id"] == "example-sim")
        assert sim["source_count"] == "2", sim  # list row + repository (two records share the repository URL)
        assert "github_topics" in sim["source_types"] and sim["country_region"] == "Germany" and sim["region"] == "Europe", sim
        router = next(r for r in rows if r["tool_id"] == "example-router")  # found only by the topic search
        assert (router["country_region"], router["region"], router["license_model"]) == ("Japan", "Asia", "open-source"), router
        assert (router["latest_version"], router["category"], router["additional_categories"]) == \
            ("v0.3.1", "place-and-route", "timing-signoff"), router
        assert sim["license"] == "MIT" and sim["license_model"] == "open-source", sim
        assert (sim["latest_version"], sim["latest_release_date"]) == ("v1.2.0", "2025-03-02"), sim
        assert sim["supported_platforms"] == "Linux; Windows; macOS", sim
        assert sim["additional_categories"] == "verification", sim
        forges = [r for r in rows if r["tool_id"].startswith("example-forge")]
        assert sorted(r["country_region"] for r in forges) == ["", "United States"], forges
        us = next(r for r in forges if r["country_region"])
        assert us["vendor_maintainer"] == "Example Vendor A Inc." and us["region"] == "North America", us
        assert us["vendor_canonical"] == "Example Vendor A Inc." and sim["vendor_canonical"] == "example-org", (us, sim)  # sim's vendor is its GitHub owner
        assert (root / "outputs" / "country_coverage.png").exists()
        review = json.load(open(proc / "review_queue.json"))
        assert any(x["type"] == "same_name_different_vendor" for x in review), review
        excluded = json.load(open(proc / "excluded_records.json"))
        assert [e["tool"] for e in excluded] == ["Example Sim Pro"], excluded
        prov = list(csv.DictReader(open(proc / "provenance.csv", encoding="utf-8")))
        assert sum(1 for p in prov if p["tool_id"] == "example-sim") == 3  # list, repository, topic search
        assert (root / "outputs" / "findings.md").exists() and (root / "outputs" / "tools_by_category.png").exists()
    print("PASS: pipeline fixture test")


if __name__ == "__main__":
    main()
