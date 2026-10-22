# A Worldwide EDA Tool Dataset, Built on Crucible: Project Report

**Snapshot:** 2026-10-22 · **Dataset:** `data/processed/eda_tools_clean.csv` (1,522 tools) · **Platform:** Crucible
(`igny`, foundation package 3.12.10.0), environment `eda-data`, workspace `eda-data-science`.

## 1. Summary

We built a reproducible pipeline that collects public information about EDA tools worldwide and produces one
deduplicated row per tool, with a source URL and collection date on every row. The committed snapshot has
**1,522 tools** (76 commercial, 967 open-source, 7 freeware, 472 not stated) from **2,172 source records**
across nine source types (curated lists, GitHub search and GitHub topic discovery were added to the original six). It covers **all 11 categories** (the 10 flow stages plus `hdl-design-entry`), from high-level synthesis to sign-off, PCB and FPGA,
and vendors in North America, Europe, Asia and Oceania. Everything (environment, libraries, collection,
analysis, notebook) runs through `igny`, and the workspace is locked. A fresh-machine simulation (empty
Crucible home → `igny workspace sync` → rebuild) reproduced the dataset with 0 validation errors.

## 2. Sources and collection method

| Source type (script) | Source | Records | What it contributes |
|---|---|---|---|
| published_list (`collect_published_lists.py`) | Wikipedia: *Comparison of EDA software*, *List of HDL simulators*, *List of free electronics circuit simulators* | 90 | discovery, developer, platforms, licence, latest release, formats; category from the table's own section |
| curated_list (`collect_curated_lists.py`) | three community "awesome" lists on GitHub (raw README text) | 372 | open-source tools: name, repository/website, description, category from the list's section |
| wikipedia_article (`collect_wikipedia_articles.py`) | the tool's Wikipedia infobox and Wikipedia's EDA software categories | 91 (22 algorithm titles rejected) | first release year, stable release, OS, licence, website, repository |
| vendor_origin (`collect_vendor_origin.py`) | the developer company's Wikipedia infobox | 75 | country of origin (Headquarters) |
| vendor_site (`collect_vendor_sites.py`) | official product pages (36 in the seed) | 35 | commercial IC tools absent from the lists: vendor, category, sales evidence |
| public_repository (`collect_public_repositories.py`) | GitHub REST API | 25 | SPDX licence, owner, latest release tag/date, category from repo description |
| repository_search (`collect_github_search.py`) | GitHub search API: metadata for curated-list repositories + strict topic discovery | 350 | SPDX licence, owner, homepage, description |
| documentation (`collect_documentation.py`) | official documentation pages | 7 | platform and format evidence (weak), headline category |
| github_topics (`collect_github_topics.py`) | GitHub search API over ~55 EDA topics (≥ 5 stars); 6,304 repositories searched, 1,127 kept by a written tool filter, the rest logged with a reason | 1,127 | open-source tools beyond the seed: owner, SPDX licence, category, homepage, latest release, owner country |

**Rules followed.** robots.txt is checked before every page, with ≥1.5 s between pages and ≥1 s between API
calls; the User-Agent identifies the project with a contact; only public pages are read. Because of
robots.txt, the Wikidata SPARQL endpoint and the Wikipedia APIs were **not** used, although they would have
been the richest structured sources (`data/metadata/source_manifest.json`). Failures are logged in
`data/raw/collection_log_<date>.jsonl`. In the final snapshot: Keysight's ADS page returned 403 (bot
protection); one developer article was missing (JLCPCB, 404); four developer articles had no usable
headquarters (a person, a project, Novarm, Qorvo "Greensboro").

**History: refresh on 2026-10-19 (earlier 2026-10-15 snapshot).** The vendor-site and GitHub collectors were improved and re-run. When a product
page's title and summary name no category, the page's own definition sentence ("NanoSpice is a … SPICE
simulator") is used; when a GitHub description names none, the README's title and first paragraph are used.
Without a token, the GitHub collector now waits for the hourly rate-limit reset instead of skipping repositories.
The other four sources were not re-collected, so `date_collected` is 2026-10-15 for 83 rows and 2026-10-19
for 48 rows. Each row records the date its primary source was actually read. Because the two refreshed sources
were written into the existing `_2026-10-15` files, `data/raw/SNAPSHOT_MANIFEST.json` now fingerprints every raw
file (SHA-256, record count, `date_collected` range): `vendor_site_2026-10-15.json` and
`public_repository_2026-10-15.json` show 2026-10-19 as their only collection date, and an offline rebuild stops if any
raw file no longer matches the manifest.

**Discovery by GitHub topic search (added after the snapshot was built).** The seed makes the dataset's reach
depend on a list the author wrote. `collect_github_topics.py` removes that limit for open-source tools: it searches
GitHub for EDA topics, keeps repositories that look like tools, and records only what the API states. A repository
is kept when it is not a fork or archived, has at least 5 stars (configurable), and its text carries an EDA anchor
word, a tool-like word and a keyword of the project's category rules; courses, curated lists, templates and hardware
designs (CPU cores, keyboards, boards) are rejected. Every rejection is written with its reason to
`data/raw/github_topics_skipped_<date>.json`. Limits to keep in mind: it finds only GitHub-hosted, mostly
open-source tools, so it widens the open-source side and does not fix the commercial and regional balance; the
filter is a heuristic (some tools without a category keyword, such as a bare "SystemVerilog parser", are skipped,
and a few non-tools may pass); the owner country is the owner's self-reported GitHub location and is used only when
it names a country. The tool counts in this report describe the 2026-10-22 snapshot, which did not include this collector
(`github_topics`); running it would add further open-source tools.

**Discovery seed.** Wikipedia's tables cover PCB, analog and HDL simulation well, but not the large
IC-implementation tools. `data/metadata/seed_tools.json` therefore lists 61 tool names with the URLs to read
(product page, GitHub repository, docs page, Wikipedia article). It holds **no field values**. A vendor-page
record is kept only if the page returns HTTP 200 **and** the product name appears on it.

## 3. Cleaning and deduplication

- **Normalisation** (`clean_data.py`): controlled vocabularies for category (10 flow stages), licence model,
  platforms and formats; ISO dates; years 1950 to today; URL validation. Records whose source did not return
  200 are excluded (0 in the final snapshot). Unknown values stay empty.
- **Derivation rules** (in `common.py`, applied to text the source states): category from keyword rules
  (rule order for list headings, first-mention order for a vendor's own summary sentence); licence model from
  the licence text (GPL/BSD/MIT… → open-source, proprietary/EULA → commercial, freeware → freeware) or from the
  page's own grouping; country from the developer's headquarters.
- **Deduplication** (`deduplicate_data.py`): union-find merges records that share a GitHub repository, a
  Wikipedia article, or a normalised name with a compatible vendor. The vendor check runs against the whole
  group, so an empty-vendor record cannot bridge two vendors. Field values follow a per-source priority, and
  the latest version and date come together from the single record reporting the most recent release.
  Result: **2,172 records → 1,522 tools**, 437 tools combining several sources, 88 same-source duplicates merged.
- **Vendor spelling** (`vendor_canonical`): spellings with the same normalised key share the most frequent form
  ("Cadence Design Systems" → "Cadence", "Altium (included in …)" → "Altium"). `vendor_maintainer` keeps the
  source's wording; counts and the vendor plot use `vendor_canonical`.
- **PCB rule** (`category_adjustments.json`): the keyword rules read "layout", "routing" and "timing" in their IC
  sense, so 6 of the 27 PCB tools (CADSTAR, Cadence Allegro X, EAGLE, KiCad, NI Ultiboard, pcb-rnd) had received
  place-and-route, timing-signoff or layout-physical-verification as *secondary* categories. A PCB-primary tool no
  longer gets those three IC stages as secondary categories; each removal is logged. Primary categories are unchanged;
  the any-category counts for the IC stages drop from 11 to 10 (place-and-route), 5 to 4 (timing sign-off) and 18 to
  13 (layout/physical verification).
- **Human review** (`review_queue.json`, `data/metadata/review_decisions.json`): ambiguous same-name/different-vendor
  pairs are never auto-merged. Two were confirmed with written reasons: GHDL (author vs GitHub org) and Xyce
  (Sandia vs GitHub org). One open item remains: SapWin is listed as freeware by one source and open-source by another.
- **A caught error:** the seed first linked the Wikipedia article "OpenROAD", which is Actian's 4GL business
  IDE, not the EDA tool. The vendor check refused the merge, which exposed the mistake; the link was removed.
- **Validation** (`validate_dataset.py`): schema, unique ids, valid source URL + date + provenance for every
  row, vocabularies, region ↔ country, first ≤ latest release. **0 errors**; 2 warnings (tools whose sources
  state no category: Defacto SoC Compiler, sv2v).

## 4. Findings

All numbers are from `outputs/` (generated by `scripts/run_analysis.py`) and describe **the collected
catalog**, not every EDA tool in existence.

**Tools per category** (`tools_by_category.png`). Simulation is the largest primary category (312), followed
by FPGA toolchain (226), verification (211) and PCB design (199); 27 tools have no category. Counting secondary categories, simulation appears in 570
tools and FPGA toolchain in 269, because most circuit and PCB tools also simulate. The implementation and
sign-off stages are small (P&R 31, timing/power sign-off 15, HLS 43 as primary) and almost entirely commercial.
The open-source exceptions are OpenROAD (P&R) and OpenSTA (static timing analysis).

**Commercial vs open-source** (`license_distribution.png`). 5 % commercial, 64 % open-source, under 1 % freeware,
31 % not stated (GitHub repositories without a stated licence). The open-source majority reflects the GitHub discovery, not the real market. Open-source is strongest in FPGA toolchains (4 of 6) and layout/physical verification;
commercial dominates PCB (19 of 27) and sign-off (3 of 4; OpenSTA is the open-source exception).

**Tools per region** (`tools_by_region.png`). 462 of 1,522 tools (30 %) have a documented vendor country.
Among them: North America 143 (United States 121, Canada 21), Europe 194 (Germany 49, United Kingdom 41, France 15,
Switzerland 14), Asia 101 (China 27, India 22, Japan 14), Africa 10, South America 8, Oceania 6. The US share reflects real market concentration (the
three largest EDA vendors are US-headquartered: Siemens EDA's HQ is in Oregon). It is inflated by a
measurement effect: companies have Wikipedia articles with a headquarters field, while community
open-source projects mostly don't, so open-source tools rarely get a country. Quantified
(`country_coverage.png`, `country_coverage_by_model.csv`): the vendor country is documented for 71 % of commercial
tools (54 of 76) and 29 % of open-source tools (277 of 967). For open-source tools the country is the GitHub owner's self-reported location, a weaker evidence than a company's headquarters. The regional chart is therefore a chart of
commercial vendors; it says little about where open-source EDA is built. The top three vendors (Cadence,
Synopsys, Siemens) account for 3 % of the tools that name a vendor (thousands of individual GitHub owners dilute the share).

**Release activity** (`release_activity.png`). About 3 % of tools have a documented first release year, the earliest
1973 (Berkeley SPICE), with a cluster in 1982 to 1993 (Magic, Micro-Cap, OrCAD, EAGLE, KiCad).
477 tools have a documented latest release; 331 of them released in 2024 to 2026. Release dates are filled for 31 % of tools, mostly from GitHub for open-source projects, so recency comparisons with commercial tools are biased. **Caution:** open-source dates come live
from GitHub, while commercial dates mostly come from Wikipedia infoboxes, which are often stale. Part of
this gap is a source effect, not a fact about the tools.

**Platforms and formats** (`platform_support.png`, `languages_formats.png`). Platforms are filled for 4 % of tools and
languages/formats for 10 %; see the two plots for the current counts (they were regenerated from this snapshot).

**Data completeness** (`data_completeness.png`). Category (98 %), vendor (96 %), repository URL (90 %) and licence model (69 %)
are well covered. First release year (3 %), platforms (4 %), languages/formats (10 %) and website (37 %) are the hardest to
find publicly, especially for community repositories.

## 5. Known gaps in coverage

1. **Not a census.** 1,522 tools is a large but heuristic sample: the GitHub part (1,127 tools) is selected by keyword rules, so a few non-tools pass and some tools are missed. The Wikipedia lists over-represent PCB, analog and
   HDL-simulation tools. IC implementation and sign-off tools come from a 61-entry discovery seed chosen by
   the author (the choice of *which* pages to read is human; every *value* comes from the pages).
2. **Country is known for 30 % of tools.** For commercial tools it is the vendor's Wikipedia headquarters
   (71 % known); for GitHub projects it is the owner's self-reported location (29 % known), which is weaker
   evidence and sometimes a city rather than where the project is built. Many Asian and European vendors
   (Primarius, Gowin, Efinix, Sigasi, Defacto) have no English Wikipedia article with a headquarters field.
   Africa (10) and South America (8) are present but small.
3. **Category** is rule-derived and can follow marketing wording (PCB tools no longer receive IC-only secondary
   categories, §3, but the rules remain keyword matches). Cadence now sells *Innovus+ Synthesis and
   Implementation*, so Innovus's primary category is synthesis, with P&R as additional. Bambu (an HLS tool)
   is primarily `fpga-toolchain` because its description mentions FPGA first. 27 tools state no category.
4. **Release data**: commercial versions are often stale or missing; tag-only GitHub projects have a version
   but no date.
5. **Documentation evidence is weak** (mentions, not guarantees) and only used for platforms and formats.
6. **Not-a-tool noise.** The Wikipedia categories and GitHub topics also surface some entries that are not EDA tools (for example `LittleBigPlanet 3` through a mis-linked article, or small utilities). 51 same-name or conflicting items are in `review_queue.json`; non-tools are not removed by hand because that would be an unrecorded judgement.
7. **Variability between runs.** Bot protection (Cadence pages alternately 200/403), intermittent TLS errors
   on this network, and GitHub's 60 requests/hour limit can drop records. Every drop is logged, the
   collectors retry up to 4 times, and a `GITHUB_TOKEN` removes the GitHub limit.

## 6. Where Crucible fell short for data-science work

1. **No pandas** (nor scipy, seaborn, scikit-learn, requests or beautifulsoup4 as tools). Workaround:
   `csv` + `collections` + numpy, `urllib`, and our own `html.parser`-based `htmlparse.py`. That is more code
   for joins and group-bys than pandas would need.
2. **Hidden bundled dependencies.** `requests` and `bs4` are importable only because jupyterlab bundles them.
   They aren't in `crucible.lock`, so relying on them would be fragile; we didn't. Likewise, on a fresh
   machine `numpy` was imported from **matplotlib's bundled copy**, not from the numpy tool: PYTHONPATH order
   decides, so a pinned version can be silently shadowed (`check_environment.py` reports this).
3. **Isolation leak.** Crucible's Python does not disable the user site-packages: `import scipy` succeeded
   inside `igny run script` from `%APPDATA%\Python\Python312`. Mitigated with `python -s`,
   `PYTHONNOUSERSITE=1` and a fail-fast check.
4. **The lock is weak for reproducibility.** pip-family tools are recorded with `"checksum": null` (no hash
   pinning), transitive dependencies aren't listed, and every entry is `platform: windows-x86_64`, so
   reproducing on Linux/macOS from this lock is untested and may not be possible.
5. **CLI ergonomics.** `igny` wasn't on the Git-Bash PATH after installation (a `doskey` macro for cmd only);
   `igny --version` prints `dev` (the guide shows a release number); the brief's starter commands and the old
   `run_all.sh` form (`igny run -- python`) differ from the authoritative `igny run script`.
6. `igny doctor` flags Docker as missing. Harmless here (no docker-family tools), but noisy.

What worked well: `igny run script` reliably used Crucible's interpreter with the tools on the path and
captured a log of every run; `igny run jupyter nbconvert --execute` ran the notebook headless; `igny workspace
sync` rebuilt the environment on an empty Crucible home from the lock alone.

## 7. Requirements traceability

How each objective and acceptance criterion of the problem statement is met, and where the evidence is.

| Requirement | Status | Evidence / caveat |
|---|---|---|
| 1 Crucible workspace bound to its own environment | Met | `crucible.toml` (workspace `eda-data-science`, env `eda-data`) |
| 2 Data-science stack installed through `igny` | Met | numpy, matplotlib, jupyterlab in `crucible.lock`; pandas, scipy, requests, beautifulsoup4 are not catalog tools and are not used (§6) |
| 3 Public sources identified | Met | §2, `data/metadata/source_manifest.json` (robots.txt decisions included) |
| 4 Collection scripts run through `igny` | Met | nine `collect_*.py`, started by `pipeline.py --collect` with Crucible's interpreter |
| 5 One cleaned dataset, duplicates merged | Met | `eda_tools_clean.csv`: 2,172 records → 1,522 tools; audit trail in `data/processed/` |
| 6 Analysis with plots | Met | 9 plots, 10 tables, `findings.md`, notebook |
| 7 Workspace locked | Met, with caveat | `crucible.lock` lists `windows-x86_64` only, no checksums (§6); Linux/macOS reproduction is untested |
| Coverage: commercial + open-source | Met | 76 commercial, 967 open-source, 7 freeware, 472 not stated |
| Coverage: every major flow category | Met | 11 of 11 categories |
| Coverage: North America, Europe, Asia | Met, thin | Europe 194 and Asia 101 tools with a documented country (§5); country is known for 30 % of tools |
| Accept 1: clone + `igny workspace sync` | Met | fresh-machine simulation, §1 |
| Accept 2: fresh dataset from live sources | Met | `pipeline.py -- --collect`, ≈ 10 min; blocked or flaky pages are logged, not hidden |
| Accept 3: same plots from the committed snapshot | Met | `SNAPSHOT_MANIFEST.json` is verified before a rebuild; CSV outputs are LF on every OS; two rebuilds gave identical bytes (§8) |
| Accept 4: trace any row to its URL | Met | `source_url` per row, every page in `provenance.csv` |
| Accept 5: nothing installed outside Crucible | Met by design | scripts import only the standard library, numpy and matplotlib; `check_environment.py` fails if they resolve outside Crucible |

## 8. Reproduction

```bash
igny workspace sync                                      # environment from crucible.lock
igny run script ./scripts/check_environment.py           # isolation proof
igny run script ./scripts/pipeline.py                    # rebuild from the committed snapshot (same plots as here)
igny run script ./scripts/pipeline.py -- --collect       # fresh dataset from live sources
igny run script ./tests/test_pipeline.py                 # offline test
igny run jupyter nbconvert --to notebook --execute --inplace notebooks/analysis.ipynb
```

Two consecutive rebuilds from the committed snapshot produced byte-identical PNGs and CSV (checked with MD5).
Any row is traceable: `source_url` in the dataset plus every contributing page in `data/processed/provenance.csv`
(with the fields each page reported).
