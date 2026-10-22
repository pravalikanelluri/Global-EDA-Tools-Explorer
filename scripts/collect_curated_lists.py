"""Collector 7 - community-curated lists of open-source EDA tools ("awesome" lists on GitHub).

Source type: curated_list. Each list is a Markdown README maintained by people working in the field; it is
read as plain text from raw.githubusercontent.com (no robots.txt there; not counted against the GitHub API
limit). Only the sections that list TOOLS are read (CPU designs, IP cores, PDKs, tutorials, blogs and
documentation sections are skipped); the allowed sections per list are written out in LISTS below.

Per item we record what the list states: the name (link text), the link (repository or website), the
one-line description, and the section heading. Category comes from the description via the documented
keyword rules (common.CATEGORY_RULES, earliest mention first); if the description names none, from the
section heading (rules first, then HEADING_CATEGORY for headings the rules cannot read, e.g. 'Waveform
Viewers'). Licence model only when the description itself states one ('GPLv3 VHDL compiler').
"""
import re

from common import (UNAMBIGUOUS_FORMATS, categorize, clean_text, detect_languages, empty_raw_record, ensure_dirs,
                    fetch_page, github_repo_key, join_multi, license_model_from, raw_path, today, valid_url,
                    write_json)

RAW_URL = "https://raw.githubusercontent.com/%s/HEAD/README.md"
# list -> section headings (any level) whose items are tools; items under any other heading are skipped
LISTS = {
    "aolofsson/awesome-opensource-hardware": [
        "Build Systems", "Circuit Compilers", "FPGA Compilers", "Layout Compilers", "Board Design",
        "FPGA Design", "Formal Verification", "Linters", "Register Design", "Schematics",
        "Electronics Simulators", "Verification Frameworks", "Physics", "Waveform Viewers"],
    "TM90/awesome-hwd-tools": [
        "Modelling", "Hardware Description Languages", "Wave Viewers", "Simulation", "Synthesis",
        "Timing Analysis", "Verification", "Layout Generation/ Manipulation", "Mixed Signal Design"],
    "drom/awesome-hdl": [
        "HDL simulators and compilers", "Meta HDL and Transpilers", "HLS", "Synthesis tools",
        "Visualization and Documentation generators", "HDL parsers", "Other Simulation tools",
        "Other Design Automation tools"],
}
# the list's own grouping, for headings the keyword rules cannot read (a mapping of headings, not of tools)
HEADING_CATEGORY = {
    "board design": "pcb-design", "schematics": "pcb-design", "waveform viewers": "simulation",
    "wave viewers": "simulation", "linters": "verification", "mixed signal design": "analog-mixed-signal",
    "electronics simulators": "simulation", "physics": "analog-mixed-signal", "register design": "hdl-design-entry",
}
ITEM = re.compile(r"^\s*(?:[-*+]\s+)?\[([^\]]+)\]\(([^)\s]+)\)\s*[-:–—]?\s*(.*)$")


def heading_categories(heading):
    return categorize(heading) or ([HEADING_CATEGORY[heading.lower()]] if heading.lower() in HEADING_CATEGORY else [])


def parse_list(md, allowed):
    """[(name, url, description, heading)] for link items under an allowed heading."""
    allowed_l = {a.lower() for a in allowed}
    heading, out, last = "", [], None
    for line in md.splitlines():
        h = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)
        if h:
            heading, last = clean_text(h.group(2)), None
            continue
        if heading.lower() not in allowed_l:
            continue
        m = ITEM.match(line)
        if m:
            name = clean_text(re.sub(r"[`*_]", "", m.group(1)))
            desc = clean_text(re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", m.group(3)))
            out.append([name, m.group(2), desc, heading])
            last = out[-1]
        elif last is not None and not last[2] and re.match(r"^\s+[-*+]\s+\S", line):
            # aolofsson style: the description is the indented bullet under the item
            last[2] = clean_text(re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", line.strip(" -*+")))
        elif line.strip():
            last = None
    return out


def main():
    ensure_dirs()
    records = []
    for repo, sections in LISTS.items():
        url = RAW_URL % repo
        status, body = fetch_page(url, "curated_lists", accept="text/plain")
        if status != 200:
            continue
        items = parse_list(body, sections)
        for name, link, desc, heading in items:
            link = valid_url(link)
            if not name or len(name) > 60 or not link:
                continue
            if "/" in name and github_repo_key(link):
                name = name.rsplit("/", 1)[-1]  # TM90 style 'owner/repo' link text
            cats = categorize(desc, by_position=True)
            cats += [c for c in heading_categories(heading) if c not in cats]
            gh = github_repo_key(link)
            rec = empty_raw_record(
                tool_name=name, category=cats[0] if cats else "", additional_categories=join_multi(cats[1:]),
                license_model=license_model_from(desc) if re.search(r"licen[cs]|\bl?gpl|\bbsd\b|\bmit\b|apache|open[- ]source", desc, re.I) else "",
                repository_url=("https://github.com/" + gh) if gh else "",
                website_url="" if gh else link,
                languages_formats=detect_languages(desc, only=UNAMBIGUOUS_FORMATS),
                source_url=url, source_type="curated_list", date_collected=today(), fetch_status=status)
            rec["_evidence"] = ("[%s] %s" % (heading, desc))[:300]
            records.append(rec)
        print("curated list %s: %d tool items" % (repo, len(items)))
    out = raw_path("curated_list")
    write_json(out, records)
    print("curated lists: %d records -> %s" % (len(records), out))


if __name__ == "__main__":
    main()
