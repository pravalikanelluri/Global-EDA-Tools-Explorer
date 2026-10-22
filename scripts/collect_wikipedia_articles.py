"""Collector 2 - Wikipedia article infoboxes for individual tools.

Source type: wikipedia_article. Input: every English Wikipedia article URL found by the published-list
collector for this snapshot, the 'wikipedia' links in data/metadata/seed_tools.json, and the member articles
of Wikipedia's own EDA software categories (CATEGORY_PAGES; read as ordinary /wiki/ pages, which robots.txt
allows). For a category member the category is the evidence that the article is about EDA software, so it is
kept even without an infobox (then only its name, link and opening-sentence category are recorded).

From the infobox we take only what it states: developer, initial release (-> first_release_year),
stable release (-> latest_version, latest_release_date), operating system, licence, website, repository,
and the 'Type'/'Genre' text, or else the article's opening sentence (-> category via common.CATEGORY_RULES).
Articles whose infobox describes an organisation (has 'Headquarters' / 'Industry') are not treated as tools.

Category members without an infobox are kept only if their title does not name an ALGORITHM or technique
(NOT_SOFTWARE_TITLE: 'Maze router', 'Lee router', 'Grid-based autorouter' ...): the category 'Autorouters'
holds those next to real products, and a technique is not a tool. Every rejected title is written to
data/raw/wikipedia_article_rejected_<date>.json so the rule can be audited.
"""
import re

from common import (categorize, clean_text, empty_raw_record, ensure_dirs, fetch_page, join_multi,
                    license_model_from, load_seed, norm_date, norm_license, norm_platforms, norm_year,
                    raw_path, read_json, today, valid_url, wiki_key, write_json)
from htmlparse import lead_paragraph, links_of, parse_infobox, wiki_article

CATEGORY_PAGES = [
    "https://en.wikipedia.org/wiki/Category:Electronic_design_automation_software",
    "https://en.wikipedia.org/wiki/Category:Electronic_design_automation_software_for_Linux",
    "https://en.wikipedia.org/wiki/Category:Free_electronic_design_automation_software",
    "https://en.wikipedia.org/wiki/Category:Electronic_circuit_simulators",
    "https://en.wikipedia.org/wiki/Category:Autorouters",
]
# organisations, people and file formats are not tools
ORG_LABELS = {"headquarters", "industry", "founded", "key people", "number of employees", "born", "died",
              "filename extension", "type of format"}
# titles that name a technique / algorithm / generic concept rather than a software product
NOT_SOFTWARE_TITLE = re.compile(
    r"\b(router|routing|autorouter|channel|algorithm|heuristic|minimi[sz]er|framework)\b$|"
    r"^(routing|autorouter)\b", re.I)
# ... except these category members, which are products whose title merely contains such a word
SOFTWARE_TITLE_OK = {"freestyle router", "freestyleroute", "toporouter", "topor", "toprouter",
                     "falcon framework", "espresso heuristic logic minimizer"}


def first(box, *labels):
    for lab in labels:
        for k, v in box.items():
            if k == lab or k.startswith(lab):
                return v
    return ("", [])


def external_link(links):
    for href, _ in links:
        if valid_url(href) and not re.search(r"wikipedia\.org|wikidata\.org|wikimedia\.org", href):
            return href
    return ""


def category_members(page_html):
    """[(title, article_url)] listed in the 'Pages in category' block of a category page."""
    m = re.search(r'<div id="mw-pages">(.*?)<div class="printfooter"', page_html, re.S)
    out = []
    for href, text in links_of(m.group(1) if m else ""):
        url = wiki_article(href)
        if url and text and not re.match(r"(List|Lists|Comparison|Outline) of\b", text):
            out.append((clean_text(re.sub(r"\s*\((software|EDA|electronics|simulator|program)\)$", "", text)), url))
    return out


def is_software_title(name):
    return name.lower() in SOFTWARE_TITLE_OK or not NOT_SOFTWARE_TITLE.search(name)


def targets():
    """[(tool_name, article_url, from_category)] from this snapshot's published lists, the seed and the EDA
    software categories, de-duplicated (the first source of an article wins)."""
    seen, out = set(), []
    for rec in read_json(raw_path("published_list"), []) or []:
        if rec.get("wikipedia_url") and wiki_key(rec["wikipedia_url"]) not in seen:
            seen.add(wiki_key(rec["wikipedia_url"]))
            out.append((rec["tool_name"], rec["wikipedia_url"], False))
    for t in load_seed():
        url = wiki_article(t.get("wikipedia", ""))
        if url and wiki_key(url) not in seen:
            seen.add(wiki_key(url))
            out.append((t["tool_name"], url, False))
    for cat in CATEGORY_PAGES:
        status, body = fetch_page(cat, "wikipedia_articles")
        if status != 200:
            continue
        members = category_members(body)
        print("category %s: %d articles" % (cat.rsplit(":", 1)[-1], len(members)))
        for name, url in members:
            if wiki_key(url) not in seen:
                seen.add(wiki_key(url))
                out.append((name, url, True))
    return out


def main():
    ensure_dirs()
    records, skipped, rejected = [], 0, []
    for name, url, from_category in targets():
        if from_category and not is_software_title(name):
            rejected.append({"title": name, "url": url, "reason": "title names an algorithm or technique, not a product"})
            continue
        status, body = fetch_page(url, "wikipedia_articles")
        if status != 200:
            continue
        box = parse_infobox(body)
        if (not box and not from_category) or ORG_LABELS & set(box):
            skipped += 1  # no infobox, or the link points to a company article rather than a tool
            continue
        dev_text, dev_links = first(box, "developer", "original author", "manufacturer")
        rel_text, _ = first(box, "initial release", "release")
        stable_text, _ = first(box, "stable release")
        os_text, _ = first(box, "operating system", "platform")
        lic_text, _ = first(box, "license", "licence")
        web_text, web_links = first(box, "website")
        _, repo_links = first(box, "repository")
        type_text, _ = first(box, "type", "genre")
        version = clean_text(re.split(r"\s*/\s*|;|\(", stable_text)[0]) if stable_text else ""
        lic = norm_license(lic_text.split(";")[0])
        # category: the infobox 'Type' if it names one, else the article's own opening sentence
        cats = categorize(type_text) or categorize(lead_paragraph(body), by_position=True)
        vendor_links = [wiki_article(h) for h, _ in dev_links if wiki_article(h)]
        rec = empty_raw_record(
            tool_name=name, vendor_maintainer=clean_text(dev_text.split(";")[0]),
            category=cats[0] if cats else "", additional_categories=join_multi(cats[1:]),
            license=lic, license_model=license_model_from(lic_text),
            website_url=external_link(web_links) or valid_url(web_text.replace(" ", "")),
            repository_url=external_link(repo_links), wikipedia_url=url,
            first_release_year=norm_year(rel_text), latest_version=version[:40],
            latest_release_date=norm_date(stable_text), latest_release_year=norm_year(stable_text),
            supported_platforms=norm_platforms(os_text), source_url=url,
            source_type="wikipedia_article", date_collected=today(), fetch_status=status)
        rec["vendor_wikipedia_url"] = vendor_links[0] if vendor_links else ""
        records.append(rec)
    out = raw_path("wikipedia_article")
    write_json(out, records)
    write_json(raw_path("wikipedia_article_rejected"), rejected)
    print("wikipedia articles: %d tool records (%d non-tool/no-infobox pages skipped, %d algorithm titles rejected) -> %s"
          % (len(records), skipped, len(rejected), out))


if __name__ == "__main__":
    main()
