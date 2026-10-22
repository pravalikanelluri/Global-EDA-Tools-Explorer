# Global EDA Tools Explorer - a worldwide EDA tool dataset, built on Crucible

A data-science project that collects public information about Electronic Design Automation (EDA) tools
from around the world (commercial, open-source and freeware; every flow stage; every region), cleans it
into **one row per tool** with a source URL and collection date on every row, analyses it, and plots the
results. **Everything runs through Crucible (`igny`)**: the environment, every library, every script.

Crucible is where the project *runs*, not what it *studies*: the dataset covers tools Crucible cannot
install (Synopsys, Cadence, Siemens, Zuken, …).

## Reproduce it (exact steps)

Prerequisite: the Crucible CLI `igny` (tested with foundation package 3.12.10.0, `igny --version` = `dev`).
Nothing else is installed: no system `pip`, no package manager, no PATH edits.

```bash
git clone <this-repo> global-eda-tools-explorer
cd global-eda-tools-explorer

# 1. recreate the environment exactly as locked (creates env 'eda-data', installs numpy, matplotlib, jupyterlab)
igny workspace sync
igny status                                   # Workspace eda-data-science | Bound env eda-data | Lock present

# 2. prove the run is isolated inside Crucible
igny run script ./scripts/check_environment.py

# 3a. rebuild dataset + plots from the COMMITTED snapshot (offline, deterministic -> same plots as the report)
igny run script ./scripts/pipeline.py

# 3b. OR collect a FRESH dataset from the live sources (≈ 10 min at polite request rates)
#     optional: EDA_CONTACT=<your email> for the User-Agent, GITHUB_TOKEN=<token> for >60 GitHub calls/hour
igny run script ./scripts/pipeline.py -- --collect
#     if your igny/shell rejects "-- --collect" (seen with PowerShell: "No such option"), use the environment variable:
#       PowerShell:  $env:EDA_COLLECT = "1"; igny run script ./scripts/pipeline.py
#       bash:        EDA_COLLECT=1 igny run script ./scripts/pipeline.py

# 4. tests (offline fixture test)
igny run script ./tests/test_pipeline.py

# 5. notebook (same plots, plus row tracing)
igny run jupyter lab notebooks/analysis.ipynb
igny run jupyter nbconvert --to notebook --execute --inplace notebooks/analysis.ipynb   # headless
```

Each step can also be run on its own, e.g. `igny run script ./scripts/collect_published_lists.py --log`.
Set `EDA_SNAPSHOT_DATE=YYYY-MM-DD` to process an older snapshot.

### Growing the dataset: discover more tools from GitHub

`collect_github_topics.py` finds open-source EDA tools by searching GitHub for EDA topics (eda, kicad, spice,
openroad, verilog, ...) instead of reading a fixed list. It keeps repositories that look like tools and writes every
skipped repository, with its reason, to `data/raw/github_topics_skipped_<date>.json` so the filter can be audited
(rules in the script header). Settings are environment variables because `igny` may not forward `-- --flags`.

```powershell
$env:EDA_SNAPSHOT_DATE = "2026-10-22"     # join the committed snapshot (without it the new file would be ignored)
$env:GITHUB_TOKEN = "<token>"             # recommended, never commit it: 30 instead of 10 searches/min, and it
                                          # enables the latest-release and owner-country lookups
$env:EDA_GITHUB_MIN_STARS = "5"           # optional: lower (e.g. 2) = more, noisier results
$env:EDA_GITHUB_MAX_PAGES = "5"           # optional: pages of 100 results per topic, at most 10
igny run script .\scripts\collect_github_topics.py       # roughly 15-40 minutes at polite rates
igny run script .\scripts\snapshot_manifest.py           # record the new raw files
igny run script .\scripts\pipeline.py                    # clean, deduplicate, validate, analyse
```
The collector prints how many tools it kept and why the rest were skipped; the pipeline prints the final tool count.
Repositories already in the dataset (same GitHub repository) are merged, not added twice. Commit the new raw files
together with `data/raw/SNAPSHOT_MANIFEST.json`. A full `--collect` run includes this collector too.

### How the workspace was created (already done; recorded for completeness)

```bash
igny env create eda-data
igny workspace create eda-data-science --path . --env eda-data
igny catalog --view full                      # checked which libraries exist -> requirements-notes.md
igny tool install numpy matplotlib jupyterlab
igny workspace lock                           # writes crucible.lock; commit it together with crucible.toml
```

## Pipeline

```
seed_tools.json (discovery URLs only)      Wikipedia list pages
            │                                     │
            ▼                                     ▼
 collect_vendor_sites   collect_public_repositories   collect_published_lists ─► collect_wikipedia_articles
 collect_documentation                                                         └► collect_vendor_origin
            │                         │                        │
            └────────► data/raw/<source>_<date>.json  (dated raw snapshot, never edited) ◄┘
                                      │
                       clean_data.py  (normalise, vocabularies, drop unverified sources)
                                      │
                       deduplicate_data.py  (merge -> one row per tool, provenance, review queue)
                                      │
                       validate_dataset.py  (schema, traceability, coverage)
                                      │
                       run_analysis.py / notebooks/analysis.ipynb  -> outputs/*.png, *.csv, findings.md
```

| Collector (one per source type) | Source | Gives |
|---|---|---|
| `collect_published_lists.py` | Wikipedia: Comparison of EDA software, List of HDL simulators, List of free electronics circuit simulators | discovery, developer, platform, licence, latest release, formats, category from the page's own grouping |
| `collect_wikipedia_articles.py` | each tool's Wikipedia infobox, plus members of Wikipedia's EDA software categories (algorithm titles such as "Maze router" are rejected and logged) | first release year, stable release, OS, licence, website, repository |
| `collect_vendor_origin.py` | each developer company's Wikipedia infobox | country of origin (Headquarters) |
| `collect_vendor_sites.py` | official product pages (seed) | commercial IC tools missing from the lists: vendor, category, sales evidence |
| `collect_public_repositories.py` | GitHub REST API | SPDX licence, owner, latest release tag + date |
| `collect_documentation.py` | official docs pages (seed) | platform / language mentions (weak evidence) |
| `collect_github_topics.py` | GitHub search API over EDA topics (discovery, no seed) | open-source tools nobody listed in advance: owner, SPDX licence, category, homepage; with a token also latest release and owner country |
| `collect_curated_lists.py` | three community "awesome" lists (aolofsson/awesome-opensource-hardware, TM90/awesome-hwd-tools, drom/awesome-hdl), read as raw README text | open-source tools: name, repository or website, one-line description, category from the list's own section |
| `collect_github_search.py` | GitHub search API: metadata for the repositories the curated lists name, plus strict topic discovery (>= 50 stars) | SPDX licence, owner, homepage, description for listed repositories; tools found by topic whose own description names a tool |

## Repository layout

| Path | Purpose |
|---|---|
| `crucible.toml`, `crucible.lock` | Crucible workspace + lock (generated by `igny`; commit together) |
| `data/metadata/seed_tools.json` | discovery list: tool names + URLs to read. **No field values.** |
| `data/metadata/source_manifest.json` | every source, its URLs, fields, and the robots.txt decisions |
| `data/metadata/review_decisions.json` | human-confirmed merges for review-queue items, each with its reason (never adds values) |
| `docs/` | problem statement, igny user guide, `AGENT_WORK_LOG.md`, `teacher.md`, `panel_cheatsheet.md` |
| `data/raw/` | dated raw snapshot per source + `collection_log_<date>.jsonl` (failures, robots skips, rate-limit skips) |
| `data/raw/SNAPSHOT_MANIFEST.json` | SHA-256, record count and `date_collected` range of every raw file; `pipeline.py` verifies it before an offline rebuild, so the committed snapshot cannot change unnoticed |
| `data/processed/eda_tools_clean.csv` | **the dataset** (one row per tool) |
| `data/processed/provenance.csv` | every source page behind every row, with the fields each page reported |
| `data/processed/review_queue.json`, `excluded_records.json`, `cleaning_issues.json`, `dedup_stats.json`, `category_adjustments.json` | audit trail (the last lists every category the PCB rule removed, per tool) |
| `scripts/` | collectors, `htmlparse.py` (stdlib HTML parser), clean, dedup, validate, analysis, `pipeline.py`, `check_environment.py` |
| `notebooks/analysis.ipynb` | analysis notebook (calls `run_analysis.py`) |
| `outputs/` | plots, tables, `summary.json`, `findings.md` |
| `reports/project_report.md` | the report: sources, findings, coverage gaps, Crucible shortfalls |
| `tests/` | offline fixture test |
| `archive/legacy_v1/` | the retired first version (hand-imported data), kept for reference only |

## Data model (`eda_tools_clean.csv`)

One row per tool. **Unknown values stay empty; nothing is guessed.** Multi-valued fields are sorted and
joined with `"; "`.

| Field | Meaning |
|---|---|
| `tool_id` | stable slug of the tool name |
| `tool_name`, `vendor_maintainer` | as stated by the sources (priority order in `deduplicate_data.py`) |
| `vendor_canonical` | one spelling per vendor for counting and grouping (`Cadence` = `Cadence Design Systems`; parenthetical notes dropped). `vendor_maintainer` keeps the source's wording |
| `country_region`, `region` | country of the vendor's headquarters (from its Wikipedia infobox) and its continent |
| `category`, `additional_categories` | controlled vocabulary along the flow: `hdl-design-entry` (HDL languages, generators, parsers, build systems), `high-level-synthesis`, `synthesis`, `simulation`, `verification`, `place-and-route`, `timing-signoff`, `layout-physical-verification`, `analog-mixed-signal`, `pcb-design`, `fpga-toolchain` |
| `license_model` | `commercial` / `open-source` / `freeware`, derived by documented rules from the licence text or the source's own grouping |
| `license` | licence as stated (SPDX id from GitHub where available) |
| `website_url`, `repository_url`, `wikipedia_url` | canonical public links |
| `first_release_year` | from the Wikipedia infobox "Initial release" only (never from repo creation dates) |
| `latest_version`, `latest_release_date`, `latest_release_year` | taken together from the ONE source reporting the most recent release |
| `supported_platforms` | Linux, Windows, macOS, Unix, Web/Cloud, Cross-platform |
| `languages_formats` | HDLs and design file formats (Verilog, VHDL, GDSII, Gerber, …) |
| `source_url`, `source_types`, `source_count`, `date_collected`, `source_verified` | provenance; every contributing source returned HTTP 200 |

**Trace any row:** `source_url` is the primary page; `provenance.csv` lists every page (filter by `tool_id`).

## Rules that keep the data honest

- Every value is read from a fetched public page; failed pages are logged and their records excluded.
- robots.txt is obeyed - which is why Wikipedia's API and the Wikidata SPARQL endpoint are *not* used.
- Category and licence model are **derived by written keyword rules** (`common.CATEGORY_RULES`,
  `common.license_model_from`) from what the source says - not typed in by hand.
- Dedup merges on same GitHub repo, same Wikipedia article, or same name + compatible vendor; anything
  ambiguous goes to `review_queue.json` instead of being merged.
- Raw snapshots are dated, and `data/raw/SNAPSHOT_MANIFEST.json` fingerprints them: an offline rebuild stops if a
  raw file differs from the committed one, so the analysis of a committed snapshot is reproducible.
  (The 2026-10-19 refresh re-collected two sources into files still named `_2026-10-15`; the manifest shows their
  `date_collected` range.) After a fresh `--collect`, commit the new raw files together with the new manifest.
- A tool whose primary category is `pcb-design` does not receive `place-and-route`, `timing-signoff` or
  `layout-physical-verification` as secondary categories: their keywords ("layout", "routing", "timing") also have a
  board-level meaning. Every removal is logged in `data/processed/category_adjustments.json`.
- All CSV outputs use LF line endings on every OS, so Windows and Linux rebuilds produce identical bytes.

See `reports/project_report.md` for findings, coverage gaps and where Crucible fell short.
