#!/usr/bin/env python3
"""
Altiplan scraper + offline parsing (raw JSON)

Design:
- Online scraping stores ONE row per date (smaller JSON):
    [date_iso, weekend_bool, holiday_bool, ps_inner_html]
- Line parsing runs OFFLINE on ps when needed (stats / find / optional expanded output).

Raw JSON format (no backwards compatibility):
    ["YYYY-MM-DD", true/false, true/false, "<html...>"]
"""
import argparse
import sys
import re
import json
import unicodedata
import datetime as dt
from urllib.parse import urljoin
from collections import Counter, defaultdict

from typing import Optional, List
import requests
from bs4 import BeautifulSoup
import urllib3

# tillad piping af std.output fra --expand-output og slå warnings fra ved --insecure
sys.stdout.reconfigure(encoding="utf-8")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# -----------------------------
# URLs
# -----------------------------
BASE = "https://login.altiplan.dk"
LANDING = "/webmodul/"
PERSONLIG = "/webmodul/personlig/"
AJAX = "/webmodul/wordpress/wp-admin/admin-ajax.php"
LOGOUT = "/webmodul/log-af/"

# -----------------------------
# Version/banner
# -----------------------------
BANNER = "ALTIPLAN parser v1.0 til personlig statistik af Henrik Højgaard (c) 2026"

# -----------------------------
# Parsing
# -----------------------------
ZERO_WIDTH_CATS = {"Cf"}  # unicode "format" chars (zero-width etc.)

TIME_RANGE_RE = re.compile(r"\b\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}\b")
TIME_LINE_START_RE = re.compile(r"^\s*\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}\b")
NUM_3DIGITS_RE = re.compile(r"^\d{3}$")
BR_SPLIT_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
SHIFT_RE = re.compile(
    r"\b\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}\b.*?(?=(\b\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}\b)|$)"
)

MONTH_MAP = {
    # EN short + full
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,

    # DK forkortelser (med/uden punktum)
    "jan.": 1, "feb.": 2, "mar.": 3, "apr.": 4,
    "jun.": 6, "jul.": 7, "aug.": 8, "sep.": 9, "okt.": 10, "nov.": 11, "dec.": 12,
    "okt": 10,

    # DK særtilfælde
    "maj": 5,

    # DK fulde navne
    "januar": 1, "februar": 2, "marts": 3, "april": 4, "juni": 6, "juli": 7,
    "august": 8, "september": 9, "oktober": 10, "november": 11, "december": 12,
}


def strip_invisible(s: str) -> str:
    if s is None:
        return ""
    return "".join(ch for ch in s if unicodedata.category(ch) not in ZERO_WIDTH_CATS)


def prev_year_month(y: int, m: int) -> tuple[int, int]:
    return (y - 1, 12) if m == 1 else (y, m - 1)


# -----------------------------
# DK holidays (conservative)
# -----------------------------
def easter_sunday_gregorian(year: int) -> dt.date:
    """Anonymous Gregorian algorithm."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return dt.date(year, month, day)


_holiday_cache: dict[int, set[dt.date]] = {}


def dk_public_holidays(year: int) -> set[dt.date]:
    """
    DK nationale helligdage (konservativt):
      - Nytårsdag
      - Skærtorsdag, Langfredag, Påskedag, 2. Påskedag
      - Kristi Himmelfart
      - Pinsedag, 2. Pinsedag
      - Juledag, 2. Juledag
    """
    if year in _holiday_cache:
        return _holiday_cache[year]

    e = easter_sunday_gregorian(year)
    hol = {
        dt.date(year, 1, 1),
        e - dt.timedelta(days=3),
        e - dt.timedelta(days=2),
        e,
        e + dt.timedelta(days=1),
        e + dt.timedelta(days=39),
        e + dt.timedelta(days=49),
        e + dt.timedelta(days=50),
        dt.date(year, 12, 25),
        dt.date(year, 12, 26),
    }
    _holiday_cache[year] = hol
    return hol


def is_weekend(d: dt.date) -> bool:
    return d.weekday() >= 5  # 5=lørdag, 6=søndag


def parse_day_month(text: str) -> tuple[int, int]:
    """
    Finder en dato af formen 'DD. Mon' i tekst der kan indeholde ekstra ting som '2. pinsedag'.
    Vælger den SENESTE forekomst hvor 'Mon' faktisk er en måned i MONTH_MAP.
    """
    t = strip_invisible(" ".join((text or "").split()))
    matches = re.findall(r"(\d{1,2})\.\s*([A-Za-zÆØÅæøå\.]+)", t)
    if not matches:
        raise ValueError(f"Kunne ikke parse dag/måned fra: {text!r}")

    for day_s, mon_raw in reversed(matches):
        day = int(day_s)
        mon_tok = strip_invisible(mon_raw).strip().lower()
        mon_tok = re.sub(r"[^a-zæøå\.]", "", mon_tok)

        candidates = [
            mon_tok,
            mon_tok.rstrip("."),
            mon_tok.rstrip(".")[:3],
        ]

        for c in candidates:
            if c in MONTH_MAP:
                return day, MONTH_MAP[c]

    raise ValueError(f"Ingen gyldig måned fundet i: {text!r} (matches={matches!r})")


# -----------------------------
# Offline parsing of ps (innerHTML)
# -----------------------------
# split_multi_shifts: Mest “sikkerhedsnet”. Hvis en tid allerede er på hver sin <br/>, kan man i praksis ofte undvære den. Men den hjælper hvis der stadig kommer en linje som: "07:45 - 15:30 100 15:30 - 22:00 100"
def split_multi_shifts(text_after_first_time: str) -> list[str]:
    s = (text_after_first_time or "").strip()
    if not s:
        return []
    matches = [m.group(0).strip() for m in SHIFT_RE.finditer(s)]
    return matches if matches else [s]


# split_labels: hvis man vil have BTY-an og BTY-sen som hver sit element, selv om de står på samme linje (eller hvis en upstream fejl gør at de bliver samlet).
def split_labels(prefix: str) -> list[str]:
    """
    Splitter prefix før første tid i labels.
    Regler:
      - tokens med '-' (fx O-an, BTY-sen) holdes samlet
      - UPPERCASE token (fx VITA) kan kombineres med næste token (dagtid/nat) -> "VITA dagtid"
    """
    toks = [t for t in (prefix or "").split() if t]
    out: list[str] = []
    i = 0
    while i < len(toks):
        t = toks[i]

        # Koder med bindestreg må ikke splittes
        if "-" in t:
            out.append(t)
            i += 1
            continue

        # "VITA dagtid" / "VITA nat"
        if t.isupper() and len(t) >= 2:
            if i + 1 < len(toks):
                nxt = toks[i + 1]
                if (not nxt.isupper()) and (not TIME_RANGE_RE.search(nxt)) and (not any(ch.isdigit() for ch in nxt)) and ("-" not in nxt):
                    out.append(f"{t} {nxt}")
                    i += 2
                    continue
            out.append(t)
            i += 1
            continue

        out.append(t)
        i += 1

    return out


# split_dash_pair: nødvendig hvis man vil have bf og - 700 som hver sit element, selv om de står på samme <br/>-linje.
def split_dash_pair(line: str) -> list[str]:
    """
    Splitter kun når '-' er separator med whitespace omkring, og IKKE hvis linjen indeholder tidsinterval.
    """
    s = (line or "").strip()
    if not s:
        return []
    if TIME_RANGE_RE.search(s):
        return [s]
    if re.search(r"\s-\s", s):
        left, right = re.split(r"\s-\s+", s, maxsplit=1)
        left = left.strip()
        right = right.rstrip()
        out: list[str] = []
        if left:
            out.append(left)
        if right:
            out.append("- " + right)
        return out or [s]
    return [s]

# anvender de 3 funktioner ovenfor
def extract_time_lines_from_ps(ps_html: str) -> list[str]:
    """
    Simplified offline parsing:
      - Split on <br/> (and <br>) and also on \r\n/\n
      - Then apply existing line rules:
          * If line contains time range: split into labels + shifts
          * Else: split dash-pair like "bf -   700" into ["bf", "-   700"]
    """
    s = ps_html or ""
    # normaliser typiske varianter (sikkerhed, selvom du gør det online)
    s = s.replace("</br>", "<br/>")

    # split på <br/>/<br>
    parts = [strip_invisible(p).strip() for p in BR_SPLIT_RE.split(s)]
    parts = [p for p in parts if p]

    # split også på faktiske linjeskift inde i hver part
    lines0: list[str] = []
    for p in parts:
        for sub in p.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            sub = strip_invisible(sub).strip()
            if sub:
                lines0.append(sub)

    out: list[str] = []
    for ln in lines0:
        m = TIME_RANGE_RE.search(ln)
        if m:
            prefix = ln[:m.start()].strip()
            rest = ln[m.start():].strip()
            if prefix:
                out.extend(split_labels(prefix))
            out.extend(split_multi_shifts(rest))
        else:
            out.extend(split_dash_pair(ln))

    return [x for x in (t.strip() for t in out) if x]


# simple parser uden funktionerne: split_dash_pair, split_labels, split_shifts
def extract_time_lines_from_ps_simple(ps_html: str) -> list[str]:
    s = (ps_html or "").replace("</br>", "<br/>")
    parts = [strip_invisible(p).strip() for p in BR_SPLIT_RE.split(s)]
    parts = [p for p in parts if p]

    lines0 = []
    for p in parts:
        for sub in p.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            sub = strip_invisible(sub).strip()
            if sub:
                lines0.append(sub)

    return lines0


def iter_expanded_rows(raw_rows: list[list], parse_func=extract_time_lines_from_ps):
    """
    Yields expanded rows:
        [date_iso, ln, weekend, holiday, ps]
    from raw rows:
        [date_iso, weekend, holiday, ps]
    """
    for r in raw_rows:
        if not (isinstance(r, list) and len(r) == 4):
            continue
        date_iso, weekend, holiday, ps = r
        for ln in parse_func(ps):
            yield [date_iso, ln, bool(weekend), bool(holiday), ps]


def filter_non_time_expanded(expanded_rows):
    for date_iso, text, weekend, holiday, ps in expanded_rows:
        if not TIME_LINE_START_RE.search(text or ""):
            yield [date_iso, text, weekend, holiday, ps]


def stats_for_terms(raw_rows: list[list], terms: list[str], parse_func=extract_time_lines_from_ps) -> dict[str, dict]:
    """
    Computes per-term stats on expanded text lines without materializing all expanded rows.
    Stats are for exact-match on ln.
    """
    wanted = set(terms)
    total = Counter()
    woh_total = Counter()
    days = defaultdict(set)
    days_woh = defaultdict(set)

    for date_iso, text, weekend, holiday, ps in iter_expanded_rows(raw_rows, parse_func=parse_func):
        if text not in wanted:
            continue
        total[text] += 1
        days[text].add(date_iso)
        if weekend or holiday:
            woh_total[text] += 1
            days_woh[text].add(date_iso)

    out = {}
    for t in terms:
        out[t] = {
            "term": t,
            "total": int(total[t]),
            "total_weekend_or_holiday": int(woh_total[t]),
            "unique_days": len(days[t]),
            "unique_days_weekend_or_holiday": len(days_woh[t]),
        }
    return out


# -----------------------------
# Raw JSON load/save
# -----------------------------
def load_raw_rows_from_json(path: str) -> list[list]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("Input JSON skal være en liste.")

    for idx, row in enumerate(data[:200]):  # sanity-check
        if not isinstance(row, list) or len(row) != 4:
            raise ValueError(f"Ugyldigt row-format ved index {idx}: forvent 4 felter, fik {row!r}")
        if not isinstance(row[0], str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", row[0]):
            raise ValueError(f"Ugyldig dato ved index {idx}: {row[0]!r}")
        if not isinstance(row[1], bool) or not isinstance(row[2], bool) or not isinstance(row[3], str):
            raise ValueError(f"Ugyldige typer ved index {idx}: {row!r}")

    return data


def save_raw_rows_to_json(path: str, rows: list[list]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)


# -----------------------------
# Online fetch (login + scrape)
# -----------------------------
def fetch_raw_rows_via_login(
    afdeling: str,
    brugernavn: str,
    password: str,
    months: int,
    insecure: bool,
) -> list[list]:
    """
    Returns raw rows:
        [date_iso, weekend_bool, holiday_bool, ps_inner_html]
    """
    verify_tls = not insecure
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; altiplan-login-script/3.0)",
        "Accept": "*/*",
    })

    landing_url = urljoin(BASE, LANDING)
    personlig_url = urljoin(BASE, PERSONLIG)
    ajax_url = urljoin(BASE, AJAX)
    logout_url = urljoin(BASE, LOGOUT)

    ajax_headers_landing = {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": BASE,
        "Referer": landing_url,
        "X-Requested-With": "XMLHttpRequest",
        "Sec-Fetch-Site": "same-origin",
    }
    ajax_headers_personlig = {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": BASE,
        "Referer": personlig_url,
        "X-Requested-With": "XMLHttpRequest",
        "Sec-Fetch-Site": "same-origin",
    }

    # 1) landing (establish cookies)
    r1 = s.get(landing_url, timeout=30, verify=verify_tls)
    r1.raise_for_status()

    # 2) login
    login_data = {
        "action": "submitButton",
        "Afd": afdeling,
        "Brugernavn": brugernavn,
        "Password": password,
        "rememberUser": "false",
        "debug": "false",
    }
    r2 = s.post(ajax_url, data=login_data, headers=ajax_headers_landing, timeout=30, verify=verify_tls)
    r2.raise_for_status()

    # 3) personlig
    r3 = s.get(personlig_url, timeout=30, verify=verify_tls)
    r3.raise_for_status()

    # 4) month view once up-front
    r4 = s.post(ajax_url, data={"action": "alter_from_week_to_month"}, headers=ajax_headers_personlig, timeout=30, verify=verify_tls)
    r4.raise_for_status()

    raw_rows: list[list] = []
    seen_dates: set[str] = set()

    calendar_selector = "#grid-container-calendar-31, .grid-container-calendar-31"
    expected_year = None
    expected_month = None

    try:
        for i in range(months):
            # Force month view each iteration (stabilize DOM)
            rv = s.post(ajax_url, data={"action": "alter_from_week_to_month"}, headers=ajax_headers_personlig, timeout=30, verify=verify_tls)
            rv.raise_for_status()

            r5_get = s.get(personlig_url, timeout=30, verify=verify_tls)
            r5_get.raise_for_status()

            # Fix at altiplan bruger ikke konsekvent valide html tags </br> <br> og linjeskift \r\n -> skift alle til <br/>
            html = re.sub(r"</\s*br\s*>", "<br/>", r5_get.text, flags=re.IGNORECASE)
            html = re.sub(r"<\s*br\s*>", "<br/>", html, flags=re.IGNORECASE)
            html = html.replace("\r\n", "<br/>")

            soup = BeautifulSoup(html, "html.parser")

            # data-date anchor (best-effort)
            bottom_bar = soup.select_one("#pp-bottom-bar")
            data_date_str = bottom_bar.get("data-date") if bottom_bar else None  # "YYYYMMDD"

            if data_date_str and re.fullmatch(r"\d{8}", data_date_str):
                anchor_year = int(data_date_str[0:4])
                anchor_month = int(data_date_str[4:6])
                if expected_year is None:
                    expected_year, expected_month = anchor_year, anchor_month
            else:
                if expected_year is None:
                    snippet = r5_get.text[:600]
                    raise RuntimeError(
                        f"Mangler data-date i iteration {i+1}/{months} og ingen fallback muligt. "
                        f"data_date={data_date_str!r}. Snippet:\n{snippet}"
                    )
                anchor_year, anchor_month = expected_year, expected_month

            grid_div = soup.select_one(calendar_selector)
            if grid_div is None:
                raise RuntimeError(f"Kunne ikke finde calendar grid: {calendar_selector} (iteration {i+1}/{months})")

            # all calendar cells
            day_cells = grid_div.select("div.grid-item-calendar-month")
            if not day_cells:
                raise RuntimeError(f"Ingen calendar cells fundet (iteration {i+1}/{months}).")

            # this-month cells only
            month_cells = []
            for cell in day_cells:
                cls = cell.get("class", [])
                if "last-month-item" in cls or "next-month-item" in cls:
                    continue
                month_cells.append(cell)

            if not month_cells:
                raise RuntimeError(f"Ingen this-month cells (iteration {i+1}/{months}).")

            first_date_p = month_cells[0].select_one("p.grid-item-date")
            if first_date_p is None:
                raise RuntimeError(f"Mangler p.grid-item-date i første this-month cell (iteration {i+1}/{months}).")

            _, current_month = parse_day_month(first_date_p.get_text(" ", strip=True))
            current_year = anchor_year + (1 if current_month < anchor_month else 0)

            holidays = dk_public_holidays(current_year)

            for cell in month_cells:
                date_p = cell.select_one("p.grid-item-date")
                if date_p is None:
                    continue

                day, mon = parse_day_month(date_p.get_text(" ", strip=True))
                d = dt.date(current_year, mon, day)
                date_iso = d.isoformat()

                if date_iso in seen_dates:
                    continue

                date_classes = date_p.get("class", [])
                html_holiday = "__holiday" in date_classes
                weekend = is_weekend(d)
                holiday = html_holiday or (d in holidays)

                # robust selector for the time <p>
                time_p = cell.select_one("p.grid-item-time, p[class*='grid-item-time']")
                ps = time_p.decode_contents() if time_p else ""

                raw_rows.append([date_iso, weekend, holiday, ps])
                seen_dates.add(date_iso)

            # go previous month
            r_prev = s.post(ajax_url, data={"action": "show_previous_month_hi"}, headers=ajax_headers_personlig, timeout=30, verify=verify_tls)
            r_prev.raise_for_status()

            if expected_year is not None:
                expected_year, expected_month = prev_year_month(expected_year, expected_month)

    finally:
        # 6) logout + clear cookies (best-effort)
        try:
            s.get(logout_url, timeout=30, verify=verify_tls)
        except Exception:
            pass
        try:
            s.cookies.clear()
        except Exception:
            pass

    raw_rows.sort(key=lambda r: r[0])
    return raw_rows


# -----------------------------
# CLI / output
# -----------------------------
def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Altiplan: scrape rå kalender data og/eller kør offline stats på gemt JSON.",
        epilog=BANNER,
        formatter_class=argparse.RawTextHelpFormatter
    )
    ap.add_argument("--inputfile", default=None, help="Læs raw kalender rows fra JSON fil og spring login over")
    ap.add_argument("--savefile", default=None, help="Gem raw kalender rows som JSON til den angivne fil")

    ap.add_argument("--find", action="append", default=[],
                    help='Søgeord til statistik (præcis match). Kan angives flere gange. Ex: --find "VITA dagtid"')

    ap.add_argument("--months", type=int, default=1,
                    help="Antal måneder der skal hentes (int > 0). Bruges kun ved login. Default=1")

    ap.add_argument("--afdeling", required=False, help="Afdelingskode (fx od207). Bruges kun ved login.")
    ap.add_argument("--brugernavn", required=False, help="Bruges kun ved login.")
    ap.add_argument("--password", required=False, help="Bruges kun ved login.")

    ap.add_argument("--insecure", action="store_true",
                    help="Svar til curl -k: disable TLS cert verification (frarådes). Bruges kun ved login.")

    ap.add_argument("--expand-output", action="store_true",
                    help="Print expanded rows som JSON til stdout (kan være stor), brug evt dato selektering.\r\nTillader ikke summary og find.")

    ap.add_argument("--no-summary", dest="summary", action="store_false",
                    help="Slå summeret statistik fra (default er at den vises).")
    ap.set_defaults(summary=True)

    ap.add_argument("--no-filter", action="store_true",
                    help="Slå filtrering fra i summary (default filtrerer linjer fra som starter med matematiske operatorer eller er rene 3-cifrede tal).")
    ap.add_argument("--include-time", action="store_true",
                    help="Medtag også klokkeslæt-linjer i summary (default viser kun ikke-tidslinjer).")
    ap.add_argument("--simple-parsing", action="store_true",
                    help="Brug simpel offline parsing af ps (split kun på <br/> og linjeskift).")

    ap.add_argument("--startdate", default=None,
                    help="Startdato (inkl.), format YYYY-MM-DD. Filtrerer --summary/--find/--expand-output.")
    ap.add_argument("--enddate", default=None,
                    help="Slutdato (inkl.), format YYYY-MM-DD. Filtrerer --summary/--find/--expand-output.")

    return ap


def should_skip_summary_line(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True

    # skip hvis starter med bestemte tegn
    if t[0] in {"/", "-", "*", "%", "+"}:
        return True

    # skip hvis kun er 3 tal (000-999)
    if NUM_3DIGITS_RE.match(t):
        return True

    return False


def parse_iso_date(s: Optional[str]) -> Optional[dt.date]:
    if not s:
        return None
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        raise ValueError(f"Ugyldig dato: {s!r}. Brug format YYYY-MM-DD")


def filter_raw_rows_by_date_range(raw_rows: List[List], start: Optional[dt.date], end: Optional[dt.date]) -> List[List]:
    if start is None and end is None:
        return raw_rows

    out = []
    for r in raw_rows:
        if not (isinstance(r, list) and len(r) == 4):
            continue
        date_iso = r[0]
        try:
            d = dt.date.fromisoformat(date_iso)
        except ValueError:
            continue

        if start is not None and d < start:
            continue
        if end is not None and d > end:
            continue

        out.append(r)

    return out


def main() -> None:
    ap = build_arg_parser()
    args = ap.parse_args()

    # print banner kun hvis vi ikke skal outputte ren JSON på stdout
    if not args.expand_output:
        print(BANNER)

    # --- Output precedence ---
    # savefile overrides expand-output
    if args.savefile and args.expand_output:
        print("Bemærk: --savefile overruler --expand-output (der printes ikke expanded JSON).", file=sys.stderr)
        args.expand_output = False

    # expand-output overrides find + summary (to keep stdout pure JSON)
    if args.expand_output:
        args.summary = False
        args.find = []

    # Acquire raw rows
    if args.inputfile:
        try:
            raw_rows = load_raw_rows_from_json(args.inputfile)
        except Exception as e:
            print(f"Fejl ved læsning af inputfile: {e}", file=sys.stderr)
            sys.exit(2)
    else:
        if args.months <= 0:
            ap.error("--months skal være en int > 0")

        missing = [name for name in ("afdeling", "brugernavn", "password") if not getattr(args, name)]
        if missing:
            ap.error(
                "Mangler login-argumenter: " + ", ".join(f"--{m}" for m in missing) +
                " (eller brug --inputfile <fil.json> for at springe login over)"
            )

        try:
            raw_rows = fetch_raw_rows_via_login(
                afdeling=args.afdeling,
                brugernavn=args.brugernavn,
                password=args.password,
                months=args.months,
                insecure=args.insecure,
            )
        except requests.RequestException as e:
            print(f"HTTP-fejl: {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Fejl: {e}", file=sys.stderr)
            sys.exit(1)

    # Save raw rows
    if args.savefile:
        try:
            save_raw_rows_to_json(args.savefile, raw_rows)
            print(f"=== Gemte raw output til: {args.savefile} ===")
        except Exception as e:
            print(f"Fejl ved gem til fil: {e}", file=sys.stderr)
            sys.exit(2)

    # Date range filter for stats
    try:
        start_d = parse_iso_date(args.startdate)
        end_d = parse_iso_date(args.enddate)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        sys.exit(2)

    if start_d and end_d and start_d > end_d:
        print("--startdate må ikke være efter --enddate", file=sys.stderr)
        sys.exit(2)

    raw_rows_stats = filter_raw_rows_by_date_range(raw_rows, start_d, end_d)
    parse_func = extract_time_lines_from_ps_simple if args.simple_parsing else extract_time_lines_from_ps

    # --find stats (offline parsing)
    if args.find:
        stats = stats_for_terms(raw_rows_stats, args.find, parse_func=parse_func)
        print("\n=== Specifik statistik (--find, exact match) ===")
        for term in args.find:
            st = stats[term]
            print(f"\nSøgeord: {st['term']}")
            print(f"  Total forekomster: {st['total']}")
            print(f"  Forekomster i weekend/helligdag: {st['total_weekend_or_holiday']}")
            print(f"  Unikke datoer med term: {st['unique_days']}")
            print(f"  Unikke datoer i weekend/helligdag: {st['unique_days_weekend_or_holiday']}")

    # --summary: count non-time lines (labels etc.) across all expanded rows
    if args.summary:
        counts = Counter()
        
        rows_iter = iter_expanded_rows(raw_rows_stats, parse_func=parse_func)
        if not args.include_time:
            rows_iter = filter_non_time_expanded(rows_iter)

        for row in rows_iter:
            # row = [date_iso, text, weekend, holiday, ps]
            counts[row[1]] += 1

        print("\n=== Summeret statistik (ikke-tidslinjer) ===")
        for text, n in counts.most_common():
            if not args.no_filter and should_skip_summary_line(text):
                continue
            print(n, text)
    
    # --expand-output: print expanded rows as JSON to stdout
    if args.expand_output:
        expanded = list(iter_expanded_rows(raw_rows_stats, parse_func=parse_func))
        print(json.dumps(expanded, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
