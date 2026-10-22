"""Analysis + plots from the cleaned CSV (deterministic: the same CSV always gives the same outputs).

Run:  igny run script ./scripts/run_analysis.py
Reads data/processed/eda_tools_clean.csv; writes outputs/*.png, outputs/*.csv, outputs/summary.json and
outputs/findings.md. Uses numpy + matplotlib installed through Crucible (igny tool install ...).
pandas is not in the Crucible catalog, so tables are built with csv + collections + numpy.
"""
import csv
import json
from collections import Counter

from common import CATEGORIES, OUT, PROCESSED, drop_user_site, ensure_dirs, read_json, split_multi

drop_user_site()
import numpy as np  # noqa: E402  (Crucible tool)
import matplotlib  # noqa: E402  (Crucible tool)

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# Validated reference palette (categorical slots in fixed order; text in neutral inks).
BLUE, ORANGE, AQUA, GRAY = "#2a78d6", "#eb6834", "#1baf7a", "#b9b8b2"
MODEL_COLOR = {"commercial": BLUE, "open-source": ORANGE, "freeware": AQUA, "unknown": GRAY}
MODELS = ["commercial", "open-source", "freeware", "unknown"]
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
REGIONS = ["North America", "Europe", "Asia", "Oceania", "South America", "Africa"]
COMPLETENESS_FIELDS = ["vendor_maintainer", "country_region", "category", "license_model", "license",
                       "website_url", "repository_url", "first_release_year", "latest_version",
                       "latest_release_year", "supported_platforms", "languages_formats"]

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "text.color": INK, "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlelocation": "left",
    "font.size": 9.5, "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
    "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True, "legend.frameon": False,
})


def write_table(name, header, rows):
    with open(OUT / name, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")  # LF on every OS: identical bytes on Windows and Linux
        w.writerow(header)
        w.writerows(rows)


def save(fig, name):
    fig.tight_layout()
    fig.savefig(OUT / name, dpi=150, metadata={"Software": None})  # no version stamp -> reproducible bytes
    plt.close(fig)


def hbar(ax, labels, values, color=BLUE, fmt="%d"):
    y = np.arange(len(labels))
    ax.barh(y, values, color=color, height=0.62, edgecolor=SURFACE, linewidth=2)
    ax.set_yticks(y, labels)
    ax.invert_yaxis()
    ax.grid(axis="y", visible=False)
    for yi, v in zip(y, values):
        ax.text(v, yi, " " + fmt % v, va="center", ha="left", color=INK2, fontsize=8.5)
    ax.margins(x=0.12)


def model_of(r):
    return r["license_model"] or "unknown"


def main():
    ensure_dirs()
    with open(PROCESSED / "eda_tools_clean.csv", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    total = len(rows)
    if not total:
        raise SystemExit("Dataset is empty; nothing to analyze.")
    date = max(r["date_collected"] for r in rows)

    # ---- tables ----------------------------------------------------------------------------
    cat_primary = Counter(r["category"] or "unknown" for r in rows)
    cat_any = Counter(c for r in rows for c in set([r["category"]] + split_multi(r["additional_categories"])) if c)
    cat_model = {c: Counter(model_of(r) for r in rows if r["category"] == c) for c in CATEGORIES + [""]}
    lic = Counter(model_of(r) for r in rows)
    region = Counter(r["region"] for r in rows if r["region"])
    country = Counter(r["country_region"] for r in rows if r["country_region"])
    first_year = Counter(int(r["first_release_year"]) for r in rows if r["first_release_year"])
    latest_year = Counter(int(r["latest_release_year"]) for r in rows if r["latest_release_year"])
    plat = Counter(p for r in rows for p in split_multi(r["supported_platforms"]))
    plat_model = {m: Counter(p for r in rows if model_of(r) == m for p in split_multi(r["supported_platforms"]))
                  for m in MODELS}
    langs = Counter(x for r in rows for x in split_multi(r["languages_formats"]))
    # vendors grouped by the dedup's canonical spelling ('Cadence' = 'Cadence Design Systems')
    vendors = Counter(r["vendor_canonical"] for r in rows if r["vendor_canonical"])
    top3_share = 100.0 * sum(n for _, n in vendors.most_common(3)) / max(sum(vendors.values()), 1)
    # how well is the vendor country known, per licence model? (shows how much of the regional picture is a
    # measurement effect: companies have Wikipedia headquarters fields, community projects mostly do not)
    cov = {m: (sum(1 for r in rows if model_of(r) == m),
               sum(1 for r in rows if model_of(r) == m and r["country_region"])) for m in MODELS}
    cov_pct = {m: (100.0 * k / n if n else 0.0) for m, (n, k) in cov.items()}
    filled = {f: round(100.0 * sum(1 for r in rows if r[f]) / total, 1) for f in COMPLETENESS_FIELDS}
    region_model = {g: Counter(model_of(r) for r in rows if r["region"] == g) for g in REGIONS}

    write_table("tools_by_category.csv", ["category", "primary_category_tools", "tools_any_category"] + MODELS,
                [(c, cat_primary.get(c, 0), cat_any.get(c, 0)) + tuple(cat_model[c].get(m, 0) for m in MODELS)
                 for c in CATEGORIES] + [("unknown", cat_primary.get("unknown", 0), "") +
                                         tuple(cat_model[""].get(m, 0) for m in MODELS)])
    write_table("license_distribution.csv", ["license_model", "tools", "percent"],
                [(m, lic.get(m, 0), round(100.0 * lic.get(m, 0) / total, 1)) for m in MODELS])
    write_table("tools_by_region.csv", ["region", "tools"] + MODELS,
                [(g, region.get(g, 0)) + tuple(region_model[g].get(m, 0) for m in MODELS) for g in REGIONS])
    write_table("tools_by_country.csv", ["country_region", "tools"], country.most_common())
    years = sorted(set(first_year) | set(latest_year))
    write_table("release_activity.csv", ["year", "first_releases", "latest_releases"],
                [(y, first_year.get(y, 0), latest_year.get(y, 0)) for y in years])
    write_table("data_completeness.csv", ["field", "percent_filled"], filled.items())
    write_table("platform_support.csv", ["platform", "tools"] + MODELS,
                [(p, n) + tuple(plat_model[m].get(p, 0) for m in MODELS) for p, n in plat.most_common()])
    write_table("languages_formats.csv", ["language_or_format", "tools"], langs.most_common())
    write_table("top_vendors.csv", ["vendor_canonical", "tools"], vendors.most_common(25))
    write_table("country_coverage_by_model.csv", ["license_model", "tools", "with_country", "percent_with_country"],
                [(m, cov[m][0], cov[m][1], round(cov_pct[m], 1)) for m in MODELS])

    # ---- 1. tools per category, split by licence model (stacked, flow order) -------------------
    labels = CATEGORIES + ["unknown"]
    keys = CATEGORIES + [""]
    fig, ax = plt.subplots(figsize=(8.5, 5))
    y, left = np.arange(len(labels)), np.zeros(len(labels))
    for m in MODELS:
        vals = np.array([cat_model[k].get(m, 0) for k in keys])
        ax.barh(y, vals, left=left, color=MODEL_COLOR[m], height=0.62, edgecolor=SURFACE, linewidth=2, label=m)
        left += vals
    for yi, v in zip(y, left):
        ax.text(v, yi, " %d" % v, va="center", color=INK2, fontsize=8.5)
    ax.set_yticks(y, labels)
    ax.invert_yaxis()
    ax.grid(axis="y", visible=False)
    ax.margins(x=0.1)
    ax.set_xlabel("Number of tools (primary category); rows follow the design flow, front end at the top")
    ax.set_title("EDA tools per design-flow category")
    ax.legend(title="licence model", loc="lower right")
    save(fig, "tools_by_category.png")

    # ---- 2. commercial vs open-source vs freeware ---------------------------------------------
    fig, ax = plt.subplots(figsize=(7, 3.2))
    vals = [lic.get(m, 0) for m in MODELS]
    ax.barh(MODELS, vals, color=[MODEL_COLOR[m] for m in MODELS], height=0.6, edgecolor=SURFACE, linewidth=2)
    ax.invert_yaxis()
    ax.grid(axis="y", visible=False)
    for i, v in enumerate(vals):
        ax.text(v, i, " %d (%.0f%%)" % (v, 100.0 * v / total), va="center", color=INK2, fontsize=8.5)
    ax.margins(x=0.18)
    ax.set_xlabel("Number of tools")
    ax.set_title("Commercial vs open-source vs freeware (%d tools)" % total)
    save(fig, "license_distribution.png")

    # ---- 3. tools per region and per country ----------------------------------------------------
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 4.6), gridspec_kw={"width_ratios": [1, 1.25]})
    regs = [g for g in REGIONS if region.get(g)]
    left = np.zeros(len(regs))
    for m in MODELS:
        vals = np.array([region_model[g].get(m, 0) for g in regs])
        a1.barh(regs, vals, left=left, color=MODEL_COLOR[m], height=0.6, edgecolor=SURFACE, linewidth=2, label=m)
        left += vals
    for yi, v in enumerate(left):
        a1.text(v, yi, " %d" % v, va="center", color=INK2, fontsize=8.5)
    a1.invert_yaxis()
    a1.grid(axis="y", visible=False)
    a1.margins(x=0.15)
    a1.set_title("By region of vendor origin")
    a1.legend(loc="lower right", fontsize=8)
    top = country.most_common(15)
    hbar(a2, [c for c, _ in top], [n for _, n in top])
    a2.set_title("Top countries")
    fig.suptitle("Where EDA tools come from (%d of %d tools have a documented vendor country)"
                 % (sum(region.values()), total), x=0.01, ha="left", fontsize=10, color=INK2)
    save(fig, "tools_by_region.png")

    # ---- 4. release activity over time: two panels, one shared unit, no dual axis ---------------
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(9, 5.6), sharex=True)
    lo = min(years) if years else 1980
    span = np.arange((lo // 5) * 5, (max(years) if years else 2026) + 1)
    a1.bar(span, [first_year.get(int(y), 0) for y in span], color=BLUE, width=0.8, edgecolor=SURFACE, linewidth=1)
    a1.set_title("First release year (when the tool first shipped) - %d tools with a documented year"
                 % sum(first_year.values()))
    a1.set_ylabel("tools")
    a2.bar(span, [latest_year.get(int(y), 0) for y in span], color=ORANGE, width=0.8, edgecolor=SURFACE, linewidth=1)
    a2.set_title("Year of the latest public release - %d tools with a documented release" % sum(latest_year.values()))
    a2.set_ylabel("tools")
    for a in (a1, a2):
        a.grid(axis="x", visible=False)
        a.yaxis.get_major_locator().set_params(integer=True)
    save(fig, "release_activity.png")

    # ---- 5. platform support by licence model (grouped) -----------------------------------------
    plats = [p for p, _ in plat.most_common()]
    fig, ax = plt.subplots(figsize=(8, 4))
    shown = [m for m in MODELS if any(plat_model[m].values())]
    w = 0.8 / max(len(shown), 1)
    x = np.arange(len(plats))
    for k, m in enumerate(shown):
        ax.bar(x + (k - (len(shown) - 1) / 2) * w, [plat_model[m].get(p, 0) for p in plats], w,
               color=MODEL_COLOR[m], edgecolor=SURFACE, linewidth=2, label=m)
    ax.set_xticks(x, plats)
    ax.grid(axis="x", visible=False)
    ax.yaxis.get_major_locator().set_params(integer=True)
    ax.set_ylabel("Number of tools")
    ax.set_title("Documented operating-system support, by licence model")
    ax.legend()
    save(fig, "platform_support.png")

    # ---- 6. data completeness --------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(7.5, 4.4))
    hbar(ax, list(filled), list(filled.values()), fmt="%.0f%%")
    ax.set_xlim(0, 112)
    ax.set_xlabel("% of tools with the field filled (empty = not found in any source; never guessed)")
    ax.set_title("Data completeness by field")
    save(fig, "data_completeness.png")

    # ---- 7. languages & formats, 8. top vendors ---------------------------------------------------
    for name, counter, title in (("languages_formats.png", langs, "Design languages and file formats mentioned"),
                                 ("top_vendors.png", vendors, "Top vendors / maintainers")):
        top = counter.most_common(15)
        if not top:
            continue
        fig, ax = plt.subplots(figsize=(7.5, 0.3 * len(top) + 1.4))
        hbar(ax, [k for k, _ in top], [v for _, v in top])
        ax.set_xlabel("Number of tools")
        ax.set_title(title)
        save(fig, name)

    # ---- 9. how well is the vendor country known, by licence model (a bias check on plot 3) -------------
    shown = [m for m in MODELS if cov[m][0]]
    fig, ax = plt.subplots(figsize=(7.5, 3.2))
    hbar(ax, ["%s (%d tools)" % (m, cov[m][0]) for m in shown], [cov_pct[m] for m in shown], fmt="%.0f%%")
    ax.set_xlim(0, 112)
    ax.set_xlabel("% of tools whose vendor country is documented")
    ax.set_title("Country coverage by licence model")
    save(fig, "country_coverage.png")

    # ---- summary + auto-generated findings ------------------------------------------------------
    stats = read_json(PROCESSED / "dedup_stats.json", {})
    summary = {"snapshot_date": date, "total_tools": total, "by_category_primary": dict(cat_primary),
               "by_category_any": dict(cat_any), "by_license_model": dict(lic), "by_region": dict(region),
               "by_country": dict(country), "percent_filled": filled, "dedup": stats,
               "country_coverage_percent_by_model": {m: round(cov_pct[m], 1) for m in MODELS},
               "top3_vendor_share_percent": round(top3_share, 1),
               "numpy": np.__version__, "matplotlib": matplotlib.__version__}
    with open(OUT / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, sort_keys=True)
        f.write("\n")

    def top1(c):
        return "%s (%d)" % c.most_common(1)[0] if c else "n/a"

    recent = sum(n for y, n in latest_year.items() if y >= int(date[:4]) - 2)
    worst = sorted(filled.items(), key=lambda kv: kv[1])[:3]
    lines = [
        "# Findings (auto-generated from the dataset, snapshot %s)" % date, "",
        "Generated by `scripts/run_analysis.py`; every number below is computed from "
        "`data/processed/eda_tools_clean.csv`. It describes the collected catalog, not every EDA tool in the world.", "",
        "- Tools in the dataset: **%d** (from %s source records; %s tools combine several sources)"
        % (total, stats.get("source_records", "?"), stats.get("multi_source_tools", "?")),
        "- Licence model: " + ", ".join("%s **%d**" % (m, lic.get(m, 0)) for m in MODELS),
        "- Largest primary category: **%s**; categories covered: %d of %d"
        % (top1(Counter({k: v for k, v in cat_primary.items() if k != "unknown"})),
           sum(1 for c in CATEGORIES if cat_any.get(c)), len(CATEGORIES)),
        "- Regions with documented vendor origin: " + ", ".join("%s %d" % (g, region[g]) for g in REGIONS if region.get(g)),
        "- Most represented country: **%s**" % top1(country),
        "- Vendor country is documented for: %s. The regional picture is therefore mostly a picture of commercial "
        "vendors (see `country_coverage.png`)"
        % "; ".join("%.0f%% of %s tools (%d of %d)" % (cov_pct[m], m, cov[m][1], cov[m][0])
                    for m in MODELS if cov[m][0]),
        "- Vendor concentration: the top 3 vendors account for **%.0f%%** of the tools that name a vendor"
        % top3_share,
        "- Tools with a release in the last 3 years (%d-%s): %d of %d with a documented release"
        % (int(date[:4]) - 2, date[:4], recent, sum(latest_year.values())),
        "- Earliest documented first release: %s" % (min(first_year) if first_year else "n/a"),
        "- Least complete fields: " + ", ".join("%s %.0f%% filled" % kv for kv in worst),
        "- Deduplication: %s same-source duplicates merged; manual review queue: %s item(s)"
        % (stats.get("duplicates_merged", "?"), stats.get("review_items", "?")),
    ]
    (OUT / "findings.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("analysis complete: %d tools; plots and tables in %s" % (total, OUT))


if __name__ == "__main__":
    main()
