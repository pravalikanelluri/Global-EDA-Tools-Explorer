"""Collector 8 - GitHub repository search API: metadata for listed repositories + topic-based discovery.

Source type: repository_search. Two uses of GET /search/repositories (its own limit: 10 requests/minute
without a token, 30 with GITHUB_TOKEN; it does not use the 60/hour core limit of collect_public_repositories):

  1. Metadata lookup for every GitHub repository named by the curated lists that collect_public_repositories
     does not already cover, 10 per request ('q=repo:a/b repo:c/d ...'). Each result carries the licence SPDX
     id, owner, homepage, description and topics. The list is the evidence that the repository is a tool.
  2. Discovery by GitHub topic (TOPICS, >= MIN_STARS stars, forks excluded). A topic alone is not evidence:
     'eda' is also 'exploratory data analysis', 'fpga'/'verilog' are mostly designs and IP cores. A repository
     is kept only if its OWN description (a) names a tool (TOOL_WORDS), (b) names no design/teaching/other
     subject (NOT_TOOL), and (c) names a flow stage (common.CATEGORY_RULES). The rule is strict by design:
     a missed tool is better than a CPU core or a course counted as a tool.

No release data here (that needs per-repository calls); latest release comes from collect_public_repositories
for the repositories it covers. source_url is the single-repository search URL, which returns this record.
"""
import json
import os
import re
import time
from urllib.parse import quote

from collect_public_repositories import SKIP_SPDX, repo_list
from common import (categorize, empty_raw_record, ensure_dirs, github_repo_key, join_multi, license_model_from,
                    log_event, norm_license, polite_get, raw_path, read_json, today, write_json)

SEARCH = "https://api.github.com/search/repositories?q=%s&per_page=100&page=%d"
TOPICS = ["electronic-design-automation", "eda", "fpga", "verilog", "systemverilog", "vhdl", "hdl", "asic", "vlsi",
          "pcb", "kicad", "spice", "circuit-simulator", "logic-synthesis"]
MIN_STARS = 50
TOOL_WORDS = re.compile(
    r"\b(simulators?|synthesi[sz]er|synthesis tool|compilers?|toolchains?|toolkit|tool(s|set)?|place[- ]and[- ]route|"
    r"placer|router|autorouter|linter|formatter|parser|waveform viewer|wave ?viewer|netlist|static timing|"
    r"layout (editor|viewer)|drc|lvs|schematic (editor|capture)|design automation|eda|bitstream|programmer|debugger|"
    r"emulator|viewer|editor|analy[sz]er|checker|hardware construction language|high[- ]level synthesis|"
    r"verification framework|testbench framework|model checker|equivalence checker|language server|plugin|"
    r"generator|framework|library for)\b", re.I)
NOT_TOOL = re.compile(
    r"awesome|tutorial|\bcourse|homework|\blabs?\b|\bexamples?\b|footprints?(?! generator)|symbol librar|keyboard|"
    r"risc-?v (core|cpu|processor|soc)|\bip cores?\b|\bcores?\b|\bcpu\b|processor|\bsoc\b|dev(elopment)? (kit|board)|"
    r"exploratory data|data analysis|pandas|dataframe|notebook|machine learning|neural|mobilenet|image processing|"
    r"\bmy\b|collection of|\bbook\b|resources|cheat|written in (verilog|vhdl|systemverilog)|implementation of|"
    r"\bprojects?\b|dataset|programming language(?! for hardware)|\b(on|for) (the )?(fpgas?|esp32|arduino|raspberry|"
    r"stm32)\b(?! (design|development|toolchains?|synthesis|tools?))|\busb\b|mcp server|\bai[- ]powered|\bllm|chatgpt|"
    r"\bgpt\b|\bmodules\b|\bip\b", re.I)


def is_tool(desc):
    return bool(TOOL_WORDS.search(desc) and not NOT_TOOL.search(desc) and categorize(desc))


def record(item, tool_name, discovered_by):
    desc = item.get("description") or ""
    cats = categorize(desc, by_position=True) or categorize(" ".join(item.get("topics") or []).replace("-", " "),
                                                         by_position=True)
    spdx = (item.get("license") or {}).get("spdx_id") or ""
    lic = "" if spdx in SKIP_SPDX else norm_license(spdx)
    rec = empty_raw_record(
        tool_name=tool_name, vendor_maintainer=(item.get("owner") or {}).get("login", ""),
        category=cats[0] if cats else "", additional_categories=join_multi(cats[1:]),
        license=lic, license_model=license_model_from(lic), website_url=item.get("homepage") or "",
        repository_url=item.get("html_url", ""),
        source_url="https://api.github.com/search/repositories?q=repo:" + item["full_name"],
        source_type="repository_search", date_collected=today(), fetch_status=200)
    rec["_evidence"] = desc[:300]
    rec["_discovered_by"] = discovered_by
    rec["_stars"] = item.get("stargazers_count", 0)
    return rec


def main():
    ensure_dirs()
    token = os.environ.get("GITHUB_TOKEN")
    headers = {"X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = "Bearer " + token
    delay = 2.2 if token else 6.5  # search limit: 30 / 10 requests per minute

    def search(q, page=1):
        url = SEARCH % (quote(q, safe=":/"), page)
        for _ in range(3):
            status, body, err, hdrs = polite_get(url, accept="application/vnd.github+json", delay=delay, headers=headers)
            hdrs = {k.lower(): v for k, v in hdrs.items()}
            if status in (403, 429) and hdrs.get("x-ratelimit-remaining") == "0":
                wait = min(max(int(hdrs.get("x-ratelimit-reset", "0")) - time.time() + 2, 5), 90)
                print("search rate limit: waiting %d s" % wait, flush=True)
                time.sleep(wait)
                continue
            if status != 200:
                log_event("fetch_failed", collector="github_search", url=url, status=status, error=err)
                return None
            return json.loads(body)
        log_event("skipped_rate_limit", collector="github_search", url=url)
        return None

    records, seen = [], set(r.lower() for _, r in repo_list())  # covered with release data by collector 5

    # 1. metadata for repositories named by the curated lists, 10 per request
    wanted = {}
    for rec in read_json(raw_path("curated_list"), []) or []:
        key = github_repo_key(rec.get("repository_url", ""))
        if key and key not in seen and key not in wanted:
            wanted[key] = rec["tool_name"]
    keys = sorted(wanted)
    found = 0
    for i in range(0, len(keys), 10):
        batch = keys[i:i + 10]
        res = search(" ".join("repo:" + k for k in batch) + " fork:true")
        items = (res or {}).get("items", [])
        matched = {}
        for item in items:
            if item["full_name"].lower() in batch:
                matched[item["full_name"].lower()] = item
        # a renamed/moved repository is answered under its new name: pair it with the requested key that has
        # the same repository name, or with the only key left unanswered in this batch
        rest_items = [it for it in items if it["full_name"].lower() not in batch]
        rest_keys = [k for k in batch if k not in matched]
        for item in rest_items:
            same = [k for k in rest_keys if k.split("/")[1] == item["name"].lower()]
            k = same[0] if same else (rest_keys[0] if len(rest_items) == 1 and len(rest_keys) == 1 else "")
            if k:
                matched[k] = item
                rest_keys.remove(k)
        for key, item in matched.items():
            records.append(record(item, wanted[key], "curated_list"))
            if key != item["full_name"].lower():
                records[-1]["_requested_as"] = key
            seen.update({key, item["full_name"].lower()})
            found += 1
    print("repository search: metadata for %d of %d curated-list repositories" % (found, len(keys)))

    # 2. discovery by topic, strict tool filter on the repository's own description
    discovered, candidates = 0, set()
    for topic in TOPICS:
        for page in range(1, 11):  # the search API returns at most 1,000 results per query
            res = search("topic:%s stars:>=%d fork:false" % (topic, MIN_STARS), page)
            items = (res or {}).get("items", [])
            for item in items:
                key = item["full_name"].lower()
                candidates.add(key)
                if key in seen or not is_tool(item.get("description") or ""):
                    continue
                seen.add(key)
                records.append(record(item, item["name"], "topic:%s stars>=%d" % (topic, MIN_STARS)))
                discovered += 1
            if len(items) < 100:
                break
    print("repository search: %d candidates by topic, %d kept as tools" % (len(candidates), discovered))
    out = raw_path("repository_search")
    write_json(out, records)
    print("repository search: %d records -> %s" % (len(records), out))


if __name__ == "__main__":
    main()
