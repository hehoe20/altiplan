#!/usr/bin/env python3
import unicodedata
import argparse
import sys
import requests
import re
import json
import datetime as dt
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag
from collections import Counter

BASE = "https://login.altiplan.dk"
LANDING = "/webmodul/"
PERSONLIG = "/webmodul/personlig/"
AJAX = "/webmodul/wordpress/wp-admin/admin-ajax.php"

TARGET_COOKIE_NAMES = {"PHPSESSID", "NSC_MC_TTM_mphjo.bmujqmbo*443"}

ZERO_WIDTH_CATS = {"Cf"}  # format chars (inkl. zero-width)

# Finder en vagtlinje: "07:45 - 15:30  100" evt. med ekstra tal til sidst
TIME_RANGE_RE = re.compile(r"\b\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}\b")
SHIFT_RE = re.compile(
    r"\b\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}\b.*?(?=(\b\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}\b)|$)"
)

MONTH_MAP = {
    # EN
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

    # DK (alm. forkortelser)
    "jan": 1, "jan.": 1,
    "feb": 2, "feb.": 2,
    "mar": 3, "mar.": 3,
    "apr": 4, "apr.": 4,
    "maj": 5,
    "jun": 6, "jun.": 6,
    "jul": 7, "jul.": 7,
    "aug": 8, "aug.": 8,
    "sep": 9, "sep.": 9,
    "okt": 10, "okt.": 10,
    "nov": 11, "nov.": 11,
    "dec": 12, "dec.": 12,
}

def normalize_month_token(tok: str) -> str:
    t = tok.strip().lower()
    # fjern trailing punktum hvis både varianter findes
    return t

def easter_sunday_gregorian(year: int) -> dt.date:
    """Anonymous Gregorian algorithm."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19*a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2*e + 2*i - h - k) % 7
    m = (a + 11*h + 22*l) // 451
    month = (h + l - 7*m + 114) // 31
    day = ((h + l - 7*m + 114) % 31) + 1
    return dt.date(year, month, day)

_holiday_cache: dict[int, set[dt.date]] = {}

def dk_public_holidays(year: int) -> set[dt.date]:
    """
    DK nationale helligdage (konservativt sæt):
      - Nytårsdag
      - Skærtorsdag, Langfredag, Påskedag, 2. Påskedag
      - Kristi Himmelfartsdag
      - Pinsedag, 2. Pinsedag
      - Juledag, 2. Juledag
    NB: Store Bededag er ikke med (afskaffet fra 2024). :contentReference[oaicite:1]{index=1}
    """
    if year in _holiday_cache:
        return _holiday_cache[year]

    e = easter_sunday_gregorian(year)
    hol = set()

    hol.add(dt.date(year, 1, 1))          # Nytår
    hol.add(e - dt.timedelta(days=3))     # Skærtorsdag
    hol.add(e - dt.timedelta(days=2))     # Langfredag
    hol.add(e)                            # Påskedag
    hol.add(e + dt.timedelta(days=1))     # 2. Påskedag
    hol.add(e + dt.timedelta(days=39))    # Kristi Himmelfart
    hol.add(e + dt.timedelta(days=49))    # Pinsedag
    hol.add(e + dt.timedelta(days=50))    # 2. Pinsedag
    hol.add(dt.date(year, 12, 25))        # Juledag
    hol.add(dt.date(year, 12, 26))        # 2. Juledag

    _holiday_cache[year] = hol
    return hol

def _strip_invisible(s: str) -> str:
    return "".join(ch for ch in s if unicodedata.category(ch) not in ZERO_WIDTH_CATS)

def split_multi_shifts(text_after_first_time: str) -> list[str]:
    s = text_after_first_time.strip()
    if not s:
        return []
    matches = [m.group(0).strip() for m in SHIFT_RE.finditer(s)]
    return matches if matches else [s]

def split_labels(prefix: str) -> list[str]:
    """
    Splitter prefix før første tid i "labels".
    Regler:
      - tokens med '-' (fx O-an, BTY-sen) holdes som én label
      - UPPERCASE token (fx VITA) kan kombineres med næste token (fx dagtid/nat) -> "VITA dagtid"
    """
    toks = [t for t in prefix.split() if t]
    out = []
    i = 0
    while i < len(toks):
        t = toks[i]

        # Koder med bindestreg må ALDRIG splittes
        if "-" in t:
            out.append(t)
            i += 1
            continue

        # "VITA dagtid" / "VITA nat" etc.
        if t.isupper() and len(t) >= 2:
            if i + 1 < len(toks):
                nxt = toks[i + 1]
                # kombiner kun hvis nxt er "ord" (ikke tid, ikke tal, ikke uppercase kode)
                if (not nxt.isupper()) and (not TIME_RANGE_RE.search(nxt)) and (not any(ch.isdigit() for ch in nxt)) and ("-" not in nxt):
                    out.append(f"{t} {nxt}")
                    i += 2
                    continue
            out.append(t)
            i += 1
            continue

        # fallback: behold token som selvstændig label
        out.append(t)
        i += 1

    return out

def split_dash_pair(line: str) -> list[str]:
    """
    Splitter kun når '-' er separator med whitespace omkring, og IKKE hvis linjen indeholder tidsinterval.
    Eksempler:
      "bf -   700" -> ["bf", "-   700"]
      "* -   *"    -> ["*", "-   *"]
      "/ -   /"    -> ["/", "-   /"]
    """
    s = line.strip()
    if not s:
        return []
    if TIME_RANGE_RE.search(s):
        return [s]
    if re.search(r"\s-\s", s):
        left, right = re.split(r"\s-\s+", s, maxsplit=1)
        left = left.strip()
        right = right.rstrip()
        out = []
        if left:
            out.append(left)
        if right:
            out.append("- " + right)  # bevar bindestregen som eget element
        return out or [s]
    return [s]

def extract_time_lines(time_p: Tag) -> list[str]:
    """
    1) Split på <br> ved at gå DOM children igennem
    2) Split også på indlejrede \r\n i tekstnoder
    3) Hvis en linje indeholder tidsinterval: split til labels + shifts
    4) Ellers: split "bf - 700" type
    """
    # 1) rå segmenter adskilt af <br>
    segments = []
    buf = []

    for node in time_p.contents:
        if isinstance(node, Tag) and node.name == "br":
            seg = _strip_invisible("".join(buf)).strip()
            if seg:
                segments.append(seg)
            buf = []
        elif isinstance(node, NavigableString):
            buf.append(str(node))
        else:
            try:
                buf.append(node.get_text(" ", strip=False))
            except Exception:
                pass

    tail = _strip_invisible("".join(buf)).strip()
    if tail:
        segments.append(tail)

    # 2) split segmenter yderligere på \r\n / \n (så "...\r\n15:30 - ..." bliver to linjer)
    lines0 = []
    for seg in segments:
        for sub in seg.splitlines():
            sub = _strip_invisible(sub).strip()
            if sub:
                lines0.append(sub)

    # 3) postprocess til endelige linjer
    out = []
    for ln in lines0:
        m = TIME_RANGE_RE.search(ln)
        if m:
            prefix = ln[:m.start()].strip()
            rest = ln[m.start():].strip()

            # labels fra prefix
            if prefix:
                out.extend(split_labels(prefix))

            # shifts fra rest (kan være 1..N)
            out.extend(split_multi_shifts(rest))
        else:
            out.extend(split_dash_pair(ln))

    return [x for x in (s.strip() for s in out) if x]

def parse_day_month(text: str) -> tuple[int, int]:
    """
    Finder en dato af formen 'DD. Mon' i tekst der kan indeholde ekstra ting som '2. pinsedag'.
    Vælger den SENESTE forekomst hvor 'Mon' faktisk er en måned i MONTH_MAP.
    """
    t = _strip_invisible(" ".join(text.split()))

    matches = re.findall(r"(\d{1,2})\.\s*([A-Za-zÆØÅæøå\.]+)", t)
    if not matches:
        raise ValueError(f"Kunne ikke parse dag/måned fra: {text!r}")

    # Gå baglæns og vælg første match der kan mappes til en måned
    for day_s, mon_raw in reversed(matches):
        day = int(day_s)

        mon_tok = _strip_invisible(mon_raw).strip().lower()
        mon_tok = re.sub(r"[^a-zæøå\.]", "", mon_tok)

        candidates = [
            mon_tok,
            mon_tok.rstrip("."),
            mon_tok.rstrip(".")[:3],  # fx 'oktober' -> 'okt'
        ]

        for c in candidates:
            if c in MONTH_MAP:
                return day, MONTH_MAP[c]

    # Hvis vi ender her, var der matches, men ingen af dem var en gyldig måned
    raise ValueError(f"Ingen gyldig måned fundet i: {text!r} (matches={matches!r})")

def is_weekend(d: dt.date) -> bool:
    return d.weekday() >= 5  # 5=lørdag, 6=søndag

def count_by_text(rows):
    """
    rows: list af [date_iso, text, weekend_bool, holiday_bool]
    return: Counter hvor key=text og value=antal
    """
    return Counter(text for _, text, _, _ in rows)

def filter_non_time_rows(rows):
    """
    rows: list af [date_iso, text, weekend_bool, holiday_bool]
    returnerer kun rækker hvor text IKKE starter med et tidsinterval
    """
    return [r for r in rows if not TIME_RANGE_RE.search(r[1] or "")]

def main():
    ap = argparse.ArgumentParser(description="Altiplan login via WP admin-ajax + ekstra ajax-kald")
    ap.add_argument("--afdeling", required=True, help="Afd (fx od207)")
    ap.add_argument("--brugernavn", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--insecure", action="store_true",
                    help="Svar til curl -k: disable TLS cert verification (frarådes)")
    ap.add_argument("--months", type=int, default=1,
                help="Antal måneder der skal hentes (int > 0). Default=1")
    args = ap.parse_args()

    if args.months <= 0:
        print("--months skal være en int > 0", file=sys.stderr)
        sys.exit(2)

    verify_tls = not args.insecure
    s = requests.Session()

    # Samme “basis” som før
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; altiplan-login-script/1.0)",
        "Accept": "*/*",
    })

    landing_url = urljoin(BASE, LANDING)
    personlig_url = urljoin(BASE, PERSONLIG)
    ajax_url = urljoin(BASE, AJAX)

    # Samme header-stil som tidligere (ingen ekstra "curl-only" headers)
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

    try:
        # 1) GET landing page (etablerer ofte NSC_*/start-cookies)
        r1 = s.get(landing_url, timeout=30, verify=verify_tls)
        r1.raise_for_status()

        # 2) POST login (matcher dit første curl)
        login_data = {
            "action": "submitButton",
            "Afd": args.afdeling,
            "Brugernavn": args.brugernavn,
            "Password": args.password,
            "rememberUser": "false",
            "debug": "false",
        }

        r2 = s.post(ajax_url, data=login_data, headers=ajax_headers_landing, timeout=30, verify=verify_tls)
        r2.raise_for_status()

        # 3) GET personlig-side (flow-kontekst)
        r3 = s.get(personlig_url, timeout=30, verify=verify_tls)
        r3.raise_for_status()

        # 4) POST: alter_from_week_to_month
        alter_data = {"action": "alter_from_week_to_month"}
        r4 = s.post(ajax_url, data=alter_data, headers=ajax_headers_personlig, timeout=30, verify=verify_tls)
        r4.raise_for_status()

        all_rows = []

        calendar_selector = "#grid-container-calendar-31, .grid-container-calendar-31"

        for i in range(args.months):
            # 5a) GET personlig (HTML)
            r5_get = s.get(personlig_url, timeout=30, verify=verify_tls)
            r5_get.raise_for_status()
            soup = BeautifulSoup(r5_get.text, "html.parser")

            # 5c) data-date fra #pp-bottom-bar inde i #calendar-wrapper-id
            wrapper = soup.select_one("#calendar-wrapper-id")
            bottom_bar = wrapper.select_one("#pp-bottom-bar") if wrapper else None
            data_date_str = bottom_bar.get("data-date") if bottom_bar else None  # fx "20260126"

            if not data_date_str or not re.fullmatch(r"\d{8}", data_date_str):
                raise RuntimeError(f"Kunne ikke finde gyldig data-date i iteration {i+1}/12: {data_date_str!r}")

            anchor_year = int(data_date_str[0:4])
            anchor_month = int(data_date_str[4:6])

            grid_div = soup.select_one(calendar_selector)
            if grid_div is None:
                raise RuntimeError(f"Kunne ikke finde calendar grid: {calendar_selector} (iteration {i+1}/12)")

            # Find alle day-cells
            day_cells = grid_div.select("div.grid-item-calendar-month")
            if not day_cells:
                day_cells = grid_div.find_all("div", class_=re.compile(r"\bgrid-item-calendar-month\b"))

            # Filtrer til "kun denne måned": skip last-month-item/next-month-item
            month_cells = []
            for cell in day_cells:
                cls = cell.get("class", [])
                if "last-month-item" in cls or "next-month-item" in cls:
                    continue
                month_cells.append(cell)

            if not month_cells:
                raise RuntimeError(f"Ingen this-month cells (iteration {i+1}/12).")

            # Fastlæg month/year for denne måneds view:
            # Vi tager måneden fra første this-month cell og justerer år ift anchor (årsskifte).
            first_date_p = month_cells[0].select_one("p.grid-item-date")
            if first_date_p is None:
                raise RuntimeError(f"Mangler p.grid-item-date i første this-month cell (iteration {i+1}/12)")

            _, current_month = parse_day_month(first_date_p.get_text(" ", strip=True))

            # Hvis current_month < anchor_month => vi er rullet ind i næste år (fx anchor=Dec, current=Jan)
            current_year = anchor_year + (1 if current_month < anchor_month else 0)

            holidays = dk_public_holidays(current_year)

            # Byg rækker: dato + hver linje i teksten (splittet på <br>)
            for cell in month_cells:
                date_p = cell.select_one("p.grid-item-date")
                if date_p is None:
                    continue

                # HTML-markeret helligdag (fx __holiday på dato <p>)
                date_classes = date_p.get("class", [])
                html_holiday = "__holiday" in date_classes

                day, mon = parse_day_month(date_p.get_text(" ", strip=True))
                d = dt.date(current_year, mon, day)

                weekend = is_weekend(d)
                holiday = html_holiday or (d in holidays)

                time_p = cell.select_one("p.grid-item-time")
                if time_p is None:
                    continue

                lines = extract_time_lines(time_p)

                for ln in lines:
                    all_rows.append([d.isoformat(), ln, weekend, holiday])
                    
            # 5d) POST ajax: show_previous_month_hi (skift måned for næste iteration)
            prev_data = {"action": "show_previous_month_hi"}
            r5_post = s.post(ajax_url, data=prev_data, headers=ajax_headers_personlig, timeout=30, verify=verify_tls)
            r5_post.raise_for_status()
 
    except requests.RequestException as e:
        print(f"HTTP-fejl: {e}", file=sys.stderr)
        sys.exit(1)

    # Output cookies (som før)
    jar = s.cookies
    all_cookies = {c.name: c.value for c in jar}

    relevant = {}
    for name, value in all_cookies.items():
        if name in TARGET_COOKIE_NAMES or name.startswith("NSC_") or name == "PHPSESSID":
            relevant[name] = value

    print("=== Relevant cookies (name=value) ===")
    for k, v in relevant.items():
        print(f"{k}={v}")

    # print("\n=== Login AJAX response (første 300 chars) ===")
    # print(r2.text[:300])

    # print("\n=== alter_from_week_to_month AJAX response (første 200 chars) ===")
    # print(r4.text[:200])

    # print(f"\n=== Calendar rows ({args.months} month) ===")
    # print(json.dumps(all_rows, ensure_ascii=False, indent=2))

    print("=== Specifik statistik ===")
    count_vita_dagtid = sum(1 for _, text, _, _ in all_rows if text == "VITA dagtid")
    print("Antal 'VITA dagtid':", count_vita_dagtid)

    count_weekend_or_holiday_vita_dagtid = sum(
        1 for _, text, weekend, holiday in all_rows
        if text == "VITA dagtid" and (weekend or holiday)
    )
    print("Antal 'VITA dagtid' i weekend eller helligdag:", count_weekend_or_holiday_vita_dagtid)

    print("=== Summeret statistik ===") 
    non_time_rows = filter_non_time_rows(all_rows)
    counts = Counter(text for _, text, _, _ in non_time_rows)
    for text, n in counts.most_common():
        print(n, text)

if __name__ == "__main__":
    main()
