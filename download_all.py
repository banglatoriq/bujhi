"""
সব সাবজেক্টের সব প্রশ্ন নামানোর স্ক্রিপ্ট (resumable)

ব্যবহার:
    python download_all.py bcs-preliminary
    python download_all.py bcs-preliminary --delay 3
    python download_all.py bcs-preliminary --only বাংলা english
    python download_all.py bcs-preliminary --list        # শুধু সাবজেক্ট দেখো
"""

import argparse
import json
import os
import sys
import time

import scraper as sc

DATA_DIR = "data"


# ---------- ফাইল হেল্পার ----------

def paths(exam, subject_slug):
    d = os.path.join(DATA_DIR, exam)
    os.makedirs(d, exist_ok=True)
    safe = subject_slug.replace("/", "_")[:120]
    return (os.path.join(d, f"{safe}.json"),
            os.path.join(d, f"{safe}.state.json"))


def load_progress(data_file, state_file):
    """আগের রানে কতদূর হয়েছিল।"""
    questions, done_pages = [], set()
    if os.path.exists(data_file):
        try:
            with open(data_file, encoding="utf-8") as f:
                questions = json.load(f)
        except Exception:
            questions = []
    if os.path.exists(state_file):
        try:
            with open(state_file, encoding="utf-8") as f:
                done_pages = set(json.load(f).get("done_pages", []))
        except Exception:
            done_pages = set()
    return questions, done_pages


def save_progress(data_file, state_file, questions, done_pages, total_pages):
    tmp = data_file + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(questions, f, ensure_ascii=False, indent=1)
    os.replace(tmp, data_file)          # লেখার মাঝপথে থামলেও ফাইল নষ্ট হবে না

    with open(state_file, "w", encoding="utf-8") as f:
        json.dump({"done_pages": sorted(done_pages),
                   "total_pages": total_pages}, f)


# ---------- মূল কাজ ----------

def discover_subjects(exam):
    soup = sc.fetch(sc.build_url(exam), delay=0)
    subs = sc.get_subjects(soup)
    if not subs:
        print("⚠  সাবজেক্ট তালিকা পাওয়া যায়নি — গোটা প্রশ্নব্যাংক একসাথে নামানো হবে।")
        return [{"name": "সব", "slug": None, "count": "?"}]
    return subs


def download_subject(exam, sub, delay, selector, retries=3):
    slug = sub["slug"]
    label = sub["name"]
    data_file, state_file = paths(exam, slug or "_all")

    questions, done_pages = load_progress(data_file, state_file)

    # পেজ ১ এনে মোট পেজ জানো
    try:
        first = sc.fetch(sc.build_url(exam, slug, 1), delay=delay)
    except Exception as e:
        print(f"   ✗ পেজ ১ আনা গেল না: {e}")
        return 0
    total_pages = sc.get_total_pages(first)

    if 1 not in done_pages:
        questions += sc.parse_page(first, selector)
        done_pages.add(1)
        save_progress(data_file, state_file, questions, done_pages, total_pages)

    remaining = [p for p in range(2, total_pages + 1) if p not in done_pages]
    if not remaining:
        print(f"   ✓ আগেই সম্পূর্ণ ({len(questions)}টি প্রশ্ন)")
        return len(questions)

    print(f"   মোট {total_pages} পেজ | বাকি {len(remaining)} | "
          f"আনুমানিক {len(remaining)*delay/60:.1f} মিনিট")

    for i, page in enumerate(remaining, 1):
        got = None
        for attempt in range(retries):
            try:
                soup = sc.fetch(sc.build_url(exam, slug, page), delay=delay)
                got = sc.parse_page(soup, selector)
                break
            except Exception as e:
                wait = delay * (attempt + 2)
                print(f"\n   ! পেজ {page} ব্যর্থ ({e}) — {wait:.0f}s পরে আবার")
                time.sleep(wait)

        if got is None:
            print(f"\n   ✗ পেজ {page} বাদ দেওয়া হলো")
            continue

        questions += got
        done_pages.add(page)

        if i % 5 == 0 or i == len(remaining):
            save_progress(data_file, state_file, questions, done_pages, total_pages)

        pct = i / len(remaining) * 100
        sys.stdout.write(f"\r   [{label}] {i}/{len(remaining)} পেজ "
                         f"({pct:5.1f}%) — {len(questions)}টি প্রশ্ন")
        sys.stdout.flush()

    save_progress(data_file, state_file, questions, done_pages, total_pages)
    print(f"\n   ✓ শেষ — {len(questions)}টি প্রশ্ন → {data_file}")
    return len(questions)


def merge_all(exam):
    """সব সাবজেক্ট ফাইল এক করে merged.json।"""
    d = os.path.join(DATA_DIR, exam)
    merged, seen = [], set()
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".json") or fn.endswith(".state.json") or fn == "merged.json":
            continue
        with open(os.path.join(d, fn), encoding="utf-8") as f:
            for q in json.load(f):
                key = q.get("url") or q.get("question")
                if key and key not in seen:
                    seen.add(key)
                    merged.append(q)
    out = os.path.join(d, "merged.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=1)
    print(f"\n📦 একত্রে {len(merged)}টি অনন্য প্রশ্ন → {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("exam", help="যেমন bcs-preliminary")
    ap.add_argument("--delay", type=float, default=2.0)
    ap.add_argument("--selector", default=None, help="Card CSS selector")
    ap.add_argument("--only", nargs="*", help="নির্দিষ্ট সাবজেক্টের নাম/slug")
    ap.add_argument("--list", action="store_true", help="শুধু সাবজেক্ট তালিকা")
    args = ap.parse_args()

    print(f"পরীক্ষা: {args.exam}\nসাবজেক্ট খোঁজা হচ্ছে...\n")
    subjects = discover_subjects(args.exam)

    for s in subjects:
        print(f"  • {s['name']:<45} {s['count']:>6}   [{s['slug']}]")

    if args.list:
        return

    if args.only:
        want = [w.lower() for w in args.only]
        subjects = [s for s in subjects
                    if any(w in (s["name"] or "").lower()
                           or w in (s["slug"] or "").lower() for w in want)]
        print(f"\nফিল্টার করে {len(subjects)}টি সাবজেক্ট")

    print(f"\n{'='*60}")
    started, grand = time.time(), 0

    for n, sub in enumerate(subjects, 1):
        print(f"\n[{n}/{len(subjects)}] {sub['name']}  ({sub['count']})")
        try:
            grand += download_subject(args.exam, sub, args.delay, args.selector)
        except KeyboardInterrupt:
            print("\n\n⏸  থামানো হলো। আবার একই কমান্ড চালালে এখান থেকেই শুরু হবে।")
            return
        except Exception as e:
            print(f"   ✗ সাবজেক্ট বাদ: {e}")

    print(f"\n{'='*60}")
    print(f"সব শেষ — {grand}টি প্রশ্ন, সময় লেগেছে {(time.time()-started)/60:.1f} মিনিট")
    merge_all(args.exam)


if __name__ == "__main__":
    main()
