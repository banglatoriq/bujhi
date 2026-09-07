"""
Satt Academy scraper — ব্যক্তিগত পড়াশোনার জন্য
বুঝি (Bujhi) প্রজেক্টের ডেটা পাইপলাইন
"""

import re
import time
import requests
from bs4 import BeautifulSoup

BASE = "https://sattacademy.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}

# ---------- বিজয় → ইউনিকোড ----------

try:
    from bijoy2unicode import converter
    _conv = converter.Unicode()
except Exception:
    _conv = None


def fix_bangla(text):
    """বিজয় ANSI লেখা হলে ইউনিকোডে বদলায়, ইউনিকোড হলে হাত দেয় না।"""
    if not text or _conv is None:
        return text
    if any('\u0980' <= ch <= '\u09FF' for ch in text):
        return text          # ইতিমধ্যে ইউনিকোড
    if not any(ch.isalpha() for ch in text):
        return text          # শুধু সংখ্যা/চিহ্ন
    try:
        return _conv.convertBijoyToUnicode(text)
    except Exception:
        return text


# ---------- নেটওয়ার্ক ----------

def fetch(url, delay=2.0, timeout=30):
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    time.sleep(delay)
    return BeautifulSoup(r.text, "html.parser")


def build_url(exam_slug, subject=None, page=1):
    path = f"{BASE}/question-bank/{exam_slug}"
    path += f"/{subject}/mcq" if subject else "/mcq"
    return f"{path}?page={page}" if page > 1 else path


# ---------- সিলেক্টর খোঁজা ----------

CANDIDATE_SELECTORS = [
    "div.single-question", "div.question-card", "div.ques-item",
    "div.question", "div.card.question", "li.question",
    "div.mcq-item", "div.question-box", "div.qb-item",
]


def probe_selectors(soup):
    """কোন CSS সিলেক্টরে কয়টা ম্যাচ হচ্ছে — ডিবাগের জন্য।"""
    rows = []
    for sel in CANDIDATE_SELECTORS:
        rows.append({"selector": sel, "matched": len(soup.select(sel))})

    # প্রশ্নের লিংক ধরে অভিভাবক ট্যাগ অনুমান
    links = soup.select("a[href*='/mcq/']")
    guessed = {}
    for a in links:
        p = a.find_parent(["div", "li", "article"])
        if p and p.get("class"):
            key = f"{p.name}." + ".".join(p.get("class"))
            guessed[key] = guessed.get(key, 0) + 1
    for key, n in sorted(guessed.items(), key=lambda x: -x[1])[:8]:
        rows.append({"selector": key + "  (auto-detected)", "matched": n})
    return rows


# ---------- পার্সিং ----------

def parse_page(soup, card_selector=None):
    cards = soup.select(card_selector) if card_selector else []

    if not cards:  # ফলব্যাক: প্রশ্ন-লিংকের অভিভাবক ধরে নাও
        seen, cards = set(), []
        for a in soup.select("a[href*='/mcq/']"):
            p = a.find_parent(["div", "li", "article"])
            if p is not None and id(p) not in seen:
                seen.add(id(p))
                cards.append(p)

    out = []
    for card in cards:
        qa = card.select_one("a[href*='/mcq/']")
        if not qa:
            continue

        question = re.sub(r"^\s*\d+\s*\.\s*", "", qa.get_text(" ", strip=True))
        if len(question) < 5:
            continue

        # অপশন — সাইট Test/Reading দুই মোডে একই অপশন রেন্ডার করে, ডিডুপ লাগবে
        raw = [o.get_text(" ", strip=True)
               for o in card.select("label, .option-text, .opt, li.option")]
        seen_o, options = set(), []
        for o in raw:
            if o and o not in seen_o:
                seen_o.add(o)
                options.append(o)

        # ট্যাগ — এটাই lesson_id-র চাবি
        tags, year, subject = [], None, None
        for t in card.select("a[href*='question-bank'], a[href*='all-mcq']"):
            txt = t.get_text(" ", strip=True)
            if not txt:
                continue
            if re.fullmatch(r"(19|20)\d{2}", txt):
                year = txt
            else:
                tags.append(fix_bangla(txt))
            if "/all-mcq/" in t.get("href", ""):
                subject = fix_bangla(txt)

        out.append({
            "question": fix_bangla(question),
            "url": qa.get("href", ""),
            "options": [fix_bangla(o) for o in options[:4]],
            "topic": subject or (tags[-1] if tags else None),
            "tags": tags,
            "year": year,
        })
    return out


def get_total_pages(soup):
    nums = [int(a.get_text(strip=True))
            for a in soup.select("ul.pagination a, .pagination a")
            if a.get_text(strip=True).isdigit()]
    return max(nums) if nums else 1


def get_subjects(soup):
    """প্রশ্নব্যাংক পেজ থেকে সাবজেক্ট লিস্ট + প্রতিটির প্রশ্নসংখ্যা।"""
    subs = []
    for a in soup.select("a[href*='/question-bank/']"):
        txt = a.get_text(" ", strip=True)
        m = re.match(r"^(.+?):\s*([\d.]+k?)$", txt)
        if m:
            slug = a.get("href", "").rstrip("/").split("/")
            slug = slug[-2] if slug[-1] == "mcq" else slug[-1]
            subs.append({
                "name": fix_bangla(m.group(1)),
                "count": m.group(2),
                "slug": slug,
            })
    seen, uniq = set(), []
    for s in subs:
        if s["slug"] not in seen:
            seen.add(s["slug"])
            uniq.append(s)
    return uniq
