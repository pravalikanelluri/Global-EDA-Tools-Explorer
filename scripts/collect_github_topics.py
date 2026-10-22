"""Collector 7 - discover open-source EDA tools through GitHub topic search (public REST API).

Source type: github_topics. The seed-based collectors read pages somebody listed in advance. This one DISCOVERS
tools: it asks the GitHub search API for repositories carrying an EDA topic (eda, kicad, spice, openroad, ...),
keeps those that look like tools (rules below), and records what GitHub itself states about each repository:
description, topics, SPDX licence, owner, homepage, latest release. Nothing is typed in; every value comes from the
API response, and the repository API URL is the row's source.

What counts as a tool (heuristic, written down so it can be audited and changed):
  keep   - not a fork, not archived, at least EDA_GITHUB_MIN_STARS stars (default 5);
           the name/description/topics contain an EDA anchor word (verilog, pcb, kicad, spice, netlist, ...);
           and the description or topics match one of the project's category rules (common.CATEGORY_RULES).
  skip   - courses, tutorials, curated lists, notes, templates, dotfiles; designs rather than tools (CPU/SoC cores,
           keyboards, robots, boards); anything whose text carries no EDA anchor, no tool-like word (tool, simulator,
           compiler, linter, ...) or no category keyword.
Every skipped repository is written, with its reason, to data/raw/github_topics_skipped_<date>.json so the
filter can be audited for false negatives.

Settings (environment variables only; igny may not forward '-- --flags'):
  GITHUB_TOKEN            optional, never commit it. Raises limits and enables the enrichment below.
  EDA_GITHUB_MIN_STARS    default 5       lower it (e.g. 2) for more, noisier results
  EDA_GITHUB_MAX_PAGES    default 5       pages of 100 results per topic (the API returns at most 10 pages)
  EDA_GITHUB_ENRICH       default 1 with a token, 0 without: per kept repository one call for the latest release and
                          one call per distinct owner for the self-reported location (-> country, only when the text
                          names a country). Without a token the 60 calls/hour core limit makes this impractical.

Rate limits: the search API allows 10 requests/minute without a token and 30 with one; the collector spaces its
calls accordingly and, on a limit response, waits for the reset the API announces.
first_release_year is never inferred from the repository creation date (same rule as collect_public_repositories).
"""
import json
import os
import re
import time
from collections import Counter

from common import (categorize, clean_text, country_from_text, empty_raw_record, ensure_dirs, join_multi,
                    license_model_from, log_event, norm_license, polite_get, raw_path, today, write_json)

SEARCH = "https://api.github.com/search/repositories?q=%s&sort=stars&order=desc&per_page=100&page=%d"
USER = "https://api.github.com/users/%s"
RELEASE = "https://api.github.com/repos/%s/releases/latest"

TOPICS = [
    "eda", "electronic-design-automation", "eda-tools", "pcb", "pcb-design", "pcb-layout", "kicad", "kicad-plugin",
    "kicad-library", "schematic-capture", "circuit-simulator", "circuit-simulation", "spice", "ngspice", "analog-circuits",
    "analog-design", "fpga", "fpga-toolchain", "open-source-fpga", "bitstream", "hdl", "hardware-description-language",
    "verilog", "systemverilog", "vhdl", "chisel", "hdl-simulator", "verilator", "logic-synthesis", "high-level-synthesis",
    "hls", "place-and-route", "static-timing-analysis", "formal-verification", "equivalence-checking", "openroad",
    "asic", "vlsi", "chip-design", "integrated-circuits", "gdsii", "gds", "layout", "netlist", "rtl", "uvm",
    "hardware-verification", "design-verification", "hardware-design", "digital-design", "gerber", "pcb-manufacturing",
    "electronics", "electronic-circuits",
]

# the text must carry at least one of these: keeps 'speech synthesis', game engines and NASA's SPICE toolkit
# (a bare 'spice' is not enough: it needs circuit context) out
ANCHOR = re.compile(
    r"\b(eda|verilog|systemverilog|vhdl|hdl|rtl|fpga|asic|vlsi|pcb|kicad|schematics?|netlists?|gds|gdsii|gerber|"
    r"circuits?|ngspice|ltspice|xyce|spice (simulat\w*|netlists?|models?|circuits?|decks?)|electronic simulat\w*|"
    r"yosys|openroad|nextpnr|bitstreams?|chisel|uvm|"
    r"electronic design|hardware design|chip design|integrated circuits?|semiconductors?|logic synthesis|"
    r"high-level synthesis|place and route|place-and-route|standard cells?|tape-?out)\b", re.I)
# not tools: teaching material, lists, templates, and hardware DESIGNS (cores, boards) rather than design software
NOT_A_TOOL = re.compile(
    r"\b(courses?|tutorials?|lectures?|homework|assignments?|coursework|thesis|awesome|curated|cheat-?sheets?|"
    r"dotfiles|notes|template|boilerplate|playground|learning|workshop|slides|textbook|"
    r"(soft|hard)[- ]?cores?|ip cores?|cpu|processors?|risc-?v core|soc|microcontroller|keyboards?|robots?|drones?|badge|"
    r"arduino shield|"
    r"esp32|raspberry|breakout|devkit|dev board|reference design)\b", re.I)
# ... and the text must say it is software for doing something (tool, simulator, compiler, ...), not just a project
TOOLISH = re.compile(
    r"\b(tools?|toolchains?|toolkits?|frameworks?|compilers?|simulators?|simulations?|emulators?|synthesi[sz]ers?|"
    r"synthesis|linters?|lint|parsers?|generators?|analy[sz]ers?|analysis|checkers?|editors?|flows?|plugins?|"
    r"verifiers?|verification|routers?|placers?|converters?|translators?|viewers?|suite|software|engine|"
    r"extractors?|optimi[sz]ers?|visuali[sz]ers?|cli|api|solvers?|testbench|ide)\b", re.I)


def repo_to_record(item):
    """Turn one GitHub search result into (raw_record, None), or (None, reason) when it is not kept."""
    name = item.get("name") or ""
    desc = clean_text(item.get("description"))
    topics = " ".join(item.get("topics") or [])
    text = " ".join((name.replace("-", " ").replace("_", " "), desc, topics.replace("-", " ")))
    if item.get("fork"):
        return None, "fork"
    if item.get("archived"):
        return None, "archived"
    if not desc and not topics:
        return None, "no description or topics"
    if not ANCHOR.search(text):
        return None, "no EDA anchor word"
    if NOT_A_TOOL.search(text):
        return None, "teaching material, list or hardware design (not a tool)"
    if not TOOLISH.search(text):
        return None, "no tool-like word (looks like a design or project)"
    cats = categorize(desc, by_position=True) or categorize(topics.replace("-", " "), by_position=True)
    if not cats:
        return None, "no category keyword"
    spdx = (item.get("license") or {}).get("spdx_id") or ""
    lic = "" if spdx in ("NOASSERTION", "OTHER") else norm_license(spdx)
    repo = item.get("full_name") or ""
    rec = empty_raw_record(
        tool_name=name, vendor_maintainer=(item.get("owner") or {}).get("login", ""),
        category=cats[0], additional_categories=join_multi(cats[1:]),
        license=lic, license_model=license_model_from(lic),
        website_url=item.get("homepage") or "", repository_url=item.get("html_url") or "",
        source_url="https://api.github.com/repos/%s" % repo, source_type="github_topics",
        date_collected=today(), fetch_status=200)
    rec["_evidence"] = desc[:300]
    rec["_stars"] = item.get("stargazers_count", 0)
    rec["_topics"] = item.get("topics") or []
    return rec, None


class Api:
    """Thin rate-limit-aware GET."""

    def __init__(self, token):
        self.headers = {"X-GitHub-Api-Version": "2022-11-28"}
        if token:
            self.headers["Authorization"] = "Bearer " + token
        self.search_delay = 2.5 if token else 6.5

    def get(self, url, search=False):
        for attempt in range(4):
            status, body, err, hdrs = polite_get(url, accept="application/vnd.github+json",
                                                 delay=self.search_delay if search else 1.0, headers=self.headers)
            h = {k.lower(): v for k, v in hdrs.items()}
            if status in (403, 429) and (h.get("x-ratelimit-remaining") == "0" or h.get("retry-after")):
                wait = int(h["retry-after"]) if h.get("retry-after") else max(int(h.get("x-ratelimit-reset", 0)) - int(time.time()), 0)
                wait = min(wait + 3, 3700)
                print("rate limit: waiting %d s" % wait, flush=True)
                log_event("rate_limit_wait", collector="github_topics", url=url, seconds=wait)
                time.sleep(wait)
                continue
            if status == 200:
                try:
                    json.loads(body)
                except ValueError:  # cut-off or corrupt response: wait and try this page again
                    log_event("bad_json", collector="github_topics", url=url)
                    time.sleep(5)
                    continue
            return status, body, err
        return 0, "", "rate limit not cleared"


def main():
    ensure_dirs()
    token = os.environ.get("GITHUB_TOKEN", "")
    min_stars = int(os.environ.get("EDA_GITHUB_MIN_STARS", "5"))
    max_pages = max(1, min(10, int(os.environ.get("EDA_GITHUB_MAX_PAGES", "5"))))
    enrich = os.environ.get("EDA_GITHUB_ENRICH", "1" if token else "0") == "1"
    api = Api(token)
    kept, skipped, seen = {}, [], set()
    reasons = Counter()
    for topic in TOPICS:
        q = "topic:%s fork:false archived:false stars:>=%d" % (topic, min_stars)
        q = q.replace(" ", "+").replace(":", "%3A").replace(">=", "%3E%3D")
        total = None
        for page in range(1, max_pages + 1):
            status, body, err = api.get(SEARCH % (q, page), search=True)
            if status != 200:
                log_event("fetch_failed", collector="github_topics", topic=topic, page=page, status=status, error=err)
                print("topic %-28s page %d: HTTP %s %s" % (topic, page, status, err), flush=True)
                break
            data = json.loads(body)
            total = data.get("total_count", 0)
            items = data.get("items", [])
            for it in items:
                key = (it.get("full_name") or "").lower()
                if not key or key in seen:
                    continue
                seen.add(key)
                rec, why = repo_to_record(it)
                if rec:
                    rec["_found_by_topic"] = topic
                    kept[key] = rec
                else:
                    reasons[why] += 1
                    skipped.append({"repo": it.get("full_name"), "reason": why, "description": clean_text(it.get("description"))[:160],
                                    "stars": it.get("stargazers_count", 0), "topic": topic})
            if len(items) < 100:
                break
        print("topic %-28s total=%-6s kept so far=%d (searched %d distinct repositories)"
              % (topic, total, len(kept), len(seen)), flush=True)

    if enrich and kept:
        print("enriching %d kept repositories (latest release, owner location)..." % len(kept), flush=True)
        owners = {}
        for i, (key, rec) in enumerate(sorted(kept.items())):
            st, rb, _ = api.get(RELEASE % key)
            if st == 200:
                rel = json.loads(rb)
                rec["latest_version"] = rel.get("tag_name") or rel.get("name") or ""
                date = (rel.get("published_at") or "")[:10]
                rec["latest_release_date"], rec["latest_release_year"] = date, date[:4]
            owner = rec["vendor_maintainer"]
            if owner and owner not in owners:
                st, ub, _ = api.get(USER % owner)
                owners[owner] = country_from_text(json.loads(ub).get("location") or "") if st == 200 else ""
            rec["country_region"] = owners.get(owner, "")
            if (i + 1) % 100 == 0:
                print("  enriched %d / %d" % (i + 1, len(kept)), flush=True)
    elif kept:
        print("no GITHUB_TOKEN: skipping latest-release and owner-country enrichment "
              "(those fields stay empty; set GITHUB_TOKEN and re-run to fill them)")

    records = [kept[k] for k in sorted(kept)]
    write_json(raw_path("github_topics"), records)
    write_json(raw_path("github_topics_skipped"), sorted(skipped, key=lambda s: (s["reason"], -(s["stars"] or 0))))
    log_event("github_topics_summary", collector="github_topics", kept=len(records), searched=len(seen),
              skipped=dict(reasons), min_stars=min_stars, max_pages=max_pages, enriched=enrich)
    print("github_topics: %d tools kept of %d distinct repositories searched; skipped by reason: %s"
          % (len(records), len(seen), dict(reasons)))
    print("-> %s" % raw_path("github_topics"))


if __name__ == "__main__":
    main()
