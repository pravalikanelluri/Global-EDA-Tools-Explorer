"""Shared helpers for the Global EDA Tools Explorer pipeline (Python standard library only)."""
import datetime
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from pathlib import Path

ROOT = Path(os.environ.get("EDA_PROJECT_ROOT", Path(__file__).resolve().parent.parent))
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
META = ROOT / "data" / "metadata"
OUT = ROOT / "outputs"
REPORTS = ROOT / "reports"

USER_AGENT = "GlobalEDAToolsExplorer/1.0 (educational research project; contact: %s)" % os.environ.get(
    "EDA_CONTACT", "set-EDA_CONTACT-env-var"
)

# ---- Schema -----------------------------------------------------------------
# Multi-valued fields are stored as a sorted, "; "-joined string.
# Unknown values stay empty: nothing is guessed.
RAW_FIELDS = [
    "tool_name", "vendor_maintainer", "country_region", "category", "additional_categories",
    "license_model", "license", "website_url", "repository_url", "wikipedia_url",
    "first_release_year", "latest_version", "latest_release_date", "latest_release_year",
    "supported_platforms", "languages_formats", "source_url", "source_type", "date_collected",
    "fetch_status", "vendor_wikipedia_url",
]
FINAL_FIELDS = [
    "tool_id", "tool_name", "vendor_maintainer", "vendor_canonical", "country_region", "region", "category",
    "additional_categories", "license_model", "license", "website_url", "repository_url",
    "wikipedia_url", "first_release_year", "latest_version", "latest_release_date",
    "latest_release_year", "supported_platforms", "languages_formats", "source_url", "source_types", "date_collected",
    "source_verified", "source_count",
]
MULTI_FIELDS = ["additional_categories", "supported_platforms", "languages_formats"]

# Controlled category vocabulary, ordered along the design flow (front end -> sign-off -> board).
CATEGORIES = [
    "hdl-design-entry", "high-level-synthesis", "synthesis", "simulation", "verification", "place-and-route",
    "timing-signoff", "layout-physical-verification", "analog-mixed-signal", "pcb-design",
    "fpga-toolchain",
]
# Keyword rules applied to source text (page title, infobox 'Type', list section headings).
# Order matters: the first matching rule wins for the primary category.
CATEGORY_RULES = [
    (r"high[- ]level synthesis|\bhls\b", "high-level-synthesis"),
    (r"static timing|timing sign-?off|timing analysis|\bsta\b|primetime|tempus|power integrity|ir[- ]drop|"
     r"electromigration", "timing-signoff"),
    (r"physical verification|sign-?off verification|\bdrc\b|\blvs\b|\bdfm\b|layout (editor|viewer|verification|suite)|"
     r"\blayout\b|\bgds(ii)?\b|vlsi", "layout-physical-verification"),
    (r"place\s*(and|&)\s*route|placement|routing|floorplan|physical (design|implementation|synthesis)|rtl-to-gds(ii)?|"
     r"implementation (system|solution)|digital implementation", "place-and-route"),
    (r"formal|verification|emulation|\blint|equivalence|coverage|testbench", "verification"),
    (r"\bfpga\b|bitstream", "fpga-toolchain"),
    (r"\bspice\b|analog|mixed[- ]signal|circuit simulat|\brf\b|microwave|electromagnetic|custom (ic|design|simulation|layout)",
     "analog-mixed-signal"),
    (r"\bhdl\b|logic simulat|verilog simulat|vhdl simulat|simulat", "simulation"),
    (r"\bsynthesis\b|\bsynthesi[sz]er\b", "synthesis"),
    (r"\bpcb\b|printed circuit|circuit board", "pcb-design"),  # 'schematic' alone is also analog/IC vocabulary
    # front-end design entry: hardware languages, HDL generators/parsers, flow build systems. Last in rule order,
    # so for headings it only becomes primary when no flow-stage keyword matched
    (r"hardware (description|construction|design|generation) language|\bhcl\b|embedded in (python|scala|haskell)|"
     r"transpil|\bparsers?\b|elaborat|build system|dependency manag|register (map|generator|description|code)|"
     r"code generator|hdl generat|hardware generat|\bdsl\b|language server", "hdl-design-entry"),
]


# Stages whose keywords also have a board-level meaning ('layout', 'routing', 'timing analysis' / signal
# integrity). A tool whose PRIMARY category is pcb-design does not get these IC stages as secondary categories:
# PCB routing is not IC place-and-route. Applied (and logged) in deduplicate_data.apply_pcb_rule.
PCB_NOT_IC_STAGES = {"place-and-route", "timing-signoff", "layout-physical-verification"}


def categorize(*texts, by_position=False):
    """All categories whose rule matches the text (first = primary).

    Default order = rule order (used for list headings such as '...simulation (analog/mixed-signal)').
    by_position=True orders by where the keyword first appears, so a vendor's own summary sentence decides
    ('Design Compiler offers best-in-class RTL synthesis ... test coverage' -> synthesis, then verification).
    """
    t = " ".join(x for x in texts if x).lower()
    hits = [(m.start(), i, cat) for i, (pat, cat) in enumerate(CATEGORY_RULES) for m in [re.search(pat, t)] if m]
    hits.sort(key=(lambda h: (h[0], h[1])) if by_position else (lambda h: h[1]))
    return [cat for _, _, cat in hits]


PLATFORM_ALIASES = {
    "linux": "Linux", "gnu/linux": "Linux", "ubuntu": "Linux", "debian": "Linux", "red hat": "Linux",
    "rhel": "Linux", "centos": "Linux", "fedora": "Linux", "unix": "Unix", "posix": "Unix",
    "solaris": "Unix", "freebsd": "Unix", "*bsd": "Unix", "bsd": "Unix", "unix-like": "Unix",
    "windows": "Windows", "microsoft windows": "Windows", "win": "Windows", "win32": "Windows",
    "macos": "macOS", "mac": "macOS", "mac os": "macOS", "mac os x": "macOS", "os x": "macOS", "osx": "macOS",
    "web": "Web/Cloud", "web browser": "Web/Cloud", "browser": "Web/Cloud", "cloud": "Web/Cloud",
    "online": "Web/Cloud", "cross-platform": "Cross-platform", "any": "Cross-platform",
}
PLATFORMS = ["Linux", "Windows", "macOS", "Unix", "Web/Cloud", "Cross-platform"]

LANGUAGE_PATTERNS = [
    ("SystemVerilog", r"systemverilog|\bsv\d{4}\b|\bsv\b"), ("Verilog", r"verilog(?!-a|-ams)|\bv(1995|2001|2005)\b"),
    ("Verilog-A/AMS", r"verilog-a"), ("VHDL", r"\bvhdl"), ("SystemC", r"systemc"),
    ("SPICE", r"spice"), ("Liberty", r"\bliberty\b"), ("LEF/DEF", r"\blef\b|\bdef\b"),
    ("GDSII", r"\bgds"), ("OASIS", r"\boasis\b"), ("Gerber", r"gerber"), ("EDIF", r"\bedif\b"),
    ("IPC-2581", r"ipc-?2581"), ("ODB++", r"odb\+\+"), ("STEP", r"\bstep\b"), ("DXF", r"\bdxf\b"),
    ("Touchstone", r"touchstone"), ("SDC", r"\bsdc\b"), ("SPEF", r"\bspef\b"),
]

OSS_LICENSE = re.compile(
    r"\b(a?gpl|lgpl|bsd|mit|apache|isc|mpl|epl|cddl|artistic|cecill|eupl|zlib|unlicense|cc0|"
    r"public domain|open[- ]source|free software|ohl|solderpad|gnu|general public)\b", re.I)
LICENSE_PLACEHOLDERS = {"noassertion", "other", "none", "unknown", "n/a", "?", ""}

US_STATES = (
    "alabama alaska arizona arkansas california colorado connecticut delaware florida georgia hawaii "
    "idaho illinois indiana iowa kansas kentucky louisiana maine maryland massachusetts michigan "
    "minnesota mississippi missouri montana nebraska nevada ohio oklahoma oregon pennsylvania "
    "tennessee texas utah vermont virginia washington wisconsin wyoming"
).split() + ["new hampshire", "new jersey", "new mexico", "new york", "north carolina", "north dakota",
             "rhode island", "south carolina", "south dakota", "west virginia"]
COUNTRY_ALIASES = {
    "u.s.": "United States", "us": "United States", "usa": "United States", "u.s.a.": "United States",
    "united states": "United States", "united states of america": "United States",
    "uk": "United Kingdom", "u.k.": "United Kingdom", "england": "United Kingdom", "scotland": "United Kingdom",
    "wales": "United Kingdom", "united kingdom": "United Kingdom",
    "prc": "China", "people's republic of china": "China", "republic of korea": "South Korea", "korea": "South Korea",
    "roc": "Taiwan", "republic of china": "Taiwan", "the netherlands": "Netherlands", "holland": "Netherlands",
    "czechia": "Czech Republic", "russian federation": "Russia", "uae": "United Arab Emirates",
}
COUNTRY_REGION = {
    "United States": "North America", "Canada": "North America", "Mexico": "North America",
    "Brazil": "South America", "Argentina": "South America", "Chile": "South America",
    "United Kingdom": "Europe", "Ireland": "Europe", "France": "Europe", "Germany": "Europe",
    "Netherlands": "Europe", "Belgium": "Europe", "Luxembourg": "Europe", "Switzerland": "Europe",
    "Austria": "Europe", "Italy": "Europe", "Spain": "Europe", "Portugal": "Europe", "Sweden": "Europe",
    "Norway": "Europe", "Denmark": "Europe", "Finland": "Europe", "Iceland": "Europe", "Poland": "Europe",
    "Czech Republic": "Europe", "Slovakia": "Europe", "Hungary": "Europe", "Romania": "Europe",
    "Bulgaria": "Europe", "Greece": "Europe", "Serbia": "Europe", "Croatia": "Europe", "Slovenia": "Europe",
    "Estonia": "Europe", "Latvia": "Europe", "Lithuania": "Europe", "Ukraine": "Europe", "Belarus": "Europe",
    "Russia": "Europe", "Turkey": "Asia", "Israel": "Asia", "United Arab Emirates": "Asia",
    "Saudi Arabia": "Asia", "Iran": "Asia", "India": "Asia", "Pakistan": "Asia", "Bangladesh": "Asia",
    "Sri Lanka": "Asia", "China": "Asia", "Hong Kong": "Asia", "Taiwan": "Asia", "Japan": "Asia",
    "South Korea": "Asia", "Singapore": "Asia", "Malaysia": "Asia", "Thailand": "Asia", "Vietnam": "Asia",
    "Philippines": "Asia", "Indonesia": "Asia", "Australia": "Oceania", "New Zealand": "Oceania",
    "South Africa": "Africa", "Egypt": "Africa", "Nigeria": "Africa", "Kenya": "Africa", "Morocco": "Africa",
}


# ---- Small utilities ---------------------------------------------------------
def snapshot_date():
    return os.environ.get("EDA_SNAPSHOT_DATE") or datetime.date.today().isoformat()


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def today():
    return now_iso()[:10]


def ensure_dirs():
    for d in (RAW, PROCESSED, META, OUT, REPORTS):
        d.mkdir(parents=True, exist_ok=True)


def read_json(path, default=None):
    p = Path(path)
    if not p.exists():
        return default
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")


def log_event(kind, **info):
    """Append a collection event to data/raw/collection_log_<date>.jsonl."""
    RAW.mkdir(parents=True, exist_ok=True)
    info.update({"kind": kind, "time": now_iso()})
    with open(RAW / ("collection_log_%s.jsonl" % snapshot_date()), "a", encoding="utf-8") as f:
        f.write(json.dumps(info, ensure_ascii=False) + "\n")


def empty_raw_record(**kw):
    rec = {k: "" for k in RAW_FIELDS}
    rec.update({k: v for k, v in kw.items() if k in rec})
    return rec


def load_seed():
    return read_json(META / "seed_tools.json", default={"tools": []})["tools"]


def raw_path(source_type, date=None):
    return RAW / ("%s_%s.json" % (source_type, date or snapshot_date()))


# ---- Polite HTTP -------------------------------------------------------------
_last_request = 0.0
_robots_cache = {}


def polite_get(url, accept="*/*", delay=1.5, timeout=25, headers=None):
    """GET with a minimum delay between requests. Returns (status, body, error, response_headers)."""
    global _last_request
    wait = delay - (time.time() - _last_request)
    if wait > 0:
        time.sleep(wait)
    hdrs = {"User-Agent": USER_AGENT, "Accept": accept}
    hdrs.update(headers or {})
    # percent-encode non-ASCII characters (e.g. the en dash in /wiki/TINA–TI); already-encoded URLs are unchanged
    url = urllib.parse.quote(url, safe=":/?#[]@!$&'()*+,;=%~")
    req = urllib.request.Request(url, headers=hdrs)
    err = ""
    for attempt in range(5):  # retry transient network errors (timeouts, TLS resets) 4 times, with backoff
        if attempt:
            time.sleep(4 * attempt)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read(5_000_000)
                charset = r.headers.get_content_charset() or "utf-8"
                _last_request = time.time()
                return r.status, raw.decode(charset, "replace"), "", dict(r.headers)
        except urllib.error.HTTPError as e:  # a real HTTP answer (403, 404, ...) is not retried
            _last_request = time.time()
            return e.code, "", "HTTP %s" % e.code, dict(e.headers or {})
        except Exception as e:  # network errors, timeouts, DNS failures
            _last_request = time.time()
            err = "%s: %s" % (type(e).__name__, e)
    return 0, "", err, {}


def robots_allowed(url):
    """Check robots.txt. Missing robots.txt (4xx) = allowed; unreachable (0/5xx) = not allowed."""
    p = urllib.parse.urlparse(url)
    base = "%s://%s" % (p.scheme, p.netloc)
    if base not in _robots_cache:
        status, body, _, _ = polite_get(base + "/robots.txt", delay=1.0)
        rp = urllib.robotparser.RobotFileParser()
        if status == 200:
            rp.parse(body.splitlines())
            _robots_cache[base] = rp
        elif 400 <= status < 500:
            _robots_cache[base] = True
        else:
            _robots_cache[base] = False
    rp = _robots_cache[base]
    return rp if isinstance(rp, bool) else rp.can_fetch(USER_AGENT, url)


def fetch_page(url, collector, accept="text/html"):
    """robots.txt check + polite GET. Logs failures. Returns (status, body)."""
    if not robots_allowed(url):
        log_event("skipped_robots", collector=collector, url=url)
        return -1, ""
    status, body, err, _ = polite_get(url, accept=accept)
    if status != 200:
        log_event("fetch_failed", collector=collector, url=url, status=status, error=err)
    return status, body


# ---- Normalization -----------------------------------------------------------
def clean_text(s):
    if s is None:
        return ""
    return re.sub(r"\s+", " ", str(s)).strip()


def _key(s):
    return re.sub(r"[\s_\-/&,]+", " ", clean_text(s).lower()).strip()


def norm_category(s):
    s = clean_text(s).lower()
    return s if s in CATEGORIES else ""


def norm_license(s):
    s = re.sub(r"\[\d+\]|\(.*?\)", "", clean_text(s)).strip(" ;,.")
    s = re.sub(r"\s+licen[cs]e$", "", s, flags=re.I)
    if s.lower() in LICENSE_PLACEHOLDERS or len(s) > 60:
        return ""
    return s


def license_model_from(license_text, hint=""):
    """Derive licence model from a licence string: a documented rule, not a guess."""
    t = "%s %s" % (license_text, hint)
    if re.search(r"freeware|free of charge|gratis|free \(proprietary\)", t, re.I):
        return "freeware"
    if OSS_LICENSE.search(t):
        return "open-source"
    if re.search(r"proprietary|commercial|closed|eula|perpetual|subscription|trialware|shareware", t, re.I):
        return "commercial"
    return ""


def norm_license_model(s):
    s = _key(s)
    return {"commercial": "commercial", "proprietary": "commercial", "open source": "open-source",
            "freeware": "freeware"}.get(s, "")


def split_multi(s):
    return [clean_text(x) for x in re.split(r"[;,|]", s or "") if clean_text(x)]


def join_multi(items):
    return "; ".join(sorted({i for i in items if i}))


def norm_platforms(s):
    out = []
    for x in re.split(r"[;,|/]| and ", re.sub(r"\(.*?\)", "", s or "")):
        k = clean_text(x).lower().strip(" .")
        if k in PLATFORM_ALIASES:
            out.append(PLATFORM_ALIASES[k])
        elif k.startswith(("windows", "win ")):
            out.append("Windows")
        elif k.startswith(("linux", "ubuntu", "red hat", "rhel", "centos")):
            out.append("Linux")
        elif k.startswith(("mac", "os x")):
            out.append("macOS")
    return join_multi(out)


def detect_languages(*texts, only=None):
    """Language/format names mentioned in the texts; `only` restricts to unambiguous names."""
    t = " ".join(x for x in texts if x).lower()
    return join_multi(name for name, pat in LANGUAGE_PATTERNS
                      if (only is None or name in only) and re.search(pat, t))


# names safe to detect in long free text (no common English words such as 'step' or code words such as 'def')
UNAMBIGUOUS_FORMATS = {"SystemVerilog", "Verilog", "Verilog-A/AMS", "VHDL", "SystemC", "SPICE", "Liberty",
                       "GDSII", "OASIS", "Gerber", "EDIF", "IPC-2581", "ODB++", "Touchstone", "SPEF"}


def norm_languages(s):
    return join_multi(x for x in split_multi(s) if x in {n for n, _ in LANGUAGE_PATTERNS})


def valid_url(u):
    u = clean_text(u)
    if not u:
        return ""
    if not re.match(r"https?://", u) and re.match(r"^[\w.-]+\.[a-z]{2,}(/|$)", u):
        u = "https://" + u.replace(" ", "")
    p = urllib.parse.urlparse(u)
    return u if p.scheme in ("http", "https") and "." in p.netloc else ""


def norm_year(s):
    m = re.search(r"\b(19[5-9]\d|20\d\d)\b", str(s or ""))
    if not m:
        return ""
    y = int(m.group(1))
    return str(y) if y <= datetime.date.today().year else ""


MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july",
                                       "august", "september", "october", "november", "december"], 1)}


def norm_date(s):
    """ISO date from 'YYYY-MM-DD' or '29 August 2026' / 'August 29, 2026'; else ''."""
    s = clean_text(s)
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", s)
    if m:
        cand = m.group(0)
    else:
        m = re.search(r"\b(\d{1,2}) (%s) (\d{4})\b" % "|".join(MONTHS), s, re.I) or \
            re.search(r"\b(%s) (\d{1,2}),? (\d{4})\b" % "|".join(MONTHS), s, re.I)
        if not m:
            return ""
        g = m.groups()
        day, mon, year = (g[0], g[1], g[2]) if g[0].isdigit() else (g[1], g[0], g[2])
        cand = "%s-%02d-%02d" % (year, MONTHS[mon.lower()], int(day))
    try:
        d = datetime.date.fromisoformat(cand)
    except ValueError:
        return ""
    return cand if d <= datetime.date.today() else ""


def country_from_text(s):
    """Country from a headquarters/location string such as 'Sunnyvale, California, U.S.'."""
    parts = [clean_text(p).strip(" .").lower() for p in re.split(r"[,;]", re.sub(r"\(.*?\)", "", s or ""))]
    for p in reversed([p for p in parts if p]):
        p2 = p + "." if p in ("u.s", "u.k", "u.s.a") else p
        if p2 in COUNTRY_ALIASES:
            return COUNTRY_ALIASES[p2]
        for c in COUNTRY_REGION:
            if p == c.lower():
                return c
        if p in US_STATES:
            return "United States"
    return ""


def region_of(country):
    return COUNTRY_REGION.get(country, "")


def name_key(name):
    return re.sub(r"[^a-z0-9]", "", clean_text(name).lower())


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", clean_text(name).lower()).strip("-")


def github_repo_key(url):
    p = urllib.parse.urlparse(clean_text(url).lower())
    if p.netloc.removeprefix("www.") != "github.com":
        return ""
    parts = [x for x in p.path.split("/") if x]
    return "/".join(parts[:2]).removesuffix(".git") if len(parts) >= 2 else ""


def wiki_key(url):
    m = re.match(r"https?://en\.wikipedia\.org/wiki/([^#?]+)", clean_text(url))
    return urllib.parse.unquote(m.group(1)).lower() if m else ""


def drop_user_site():
    """Keep the interpreter isolated: never import from the user's personal site-packages."""
    import site
    user = site.getusersitepackages() if hasattr(site, "getusersitepackages") else ""
    if user:
        sys.path[:] = [p for p in sys.path if not p.startswith(user)]
