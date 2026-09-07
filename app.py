"""
বুঝি — ডেটা কালেকশন UI
চালাও:  streamlit run app.py
"""

import json
import io
from collections import Counter

import pandas as pd
import streamlit as st

import scraper as sc

st.set_page_config(page_title="বুঝি — ডেটা কালেকশন", page_icon="📚", layout="wide")
st.title("📚 বুঝি — ডেটা কালেকশন")
st.caption("ব্যক্তিগত পড়াশোনার জন্য প্রশ্ন ও টপিক সংগ্রহ")

if "questions" not in st.session_state:
    st.session_state.questions = []

# ---------------- সাইডবার ----------------
with st.sidebar:
    st.header("সেটিংস")
    exam = st.text_input("Exam slug", value="bcs-preliminary",
                         help="URL-এর /question-bank/ এর পরের অংশ")
    subject = st.text_input("Subject slug (ঐচ্ছিক)", value="")
    col_a, col_b = st.columns(2)
    start_page = col_a.number_input("শুরু পেজ", 1, 9999, 1)
    end_page = col_b.number_input("শেষ পেজ", 1, 9999, 5)
    delay = st.slider("প্রতি রিকোয়েস্টে বিরতি (সেকেন্ড)", 1.0, 5.0, 2.0, 0.5)
    selector = st.text_input("Card CSS selector (খালি = অটো)", value="")
    st.divider()
    if st.button("🗑 সব ডেটা মুছে ফেলো"):
        st.session_state.questions = []
        st.rerun()

tab1, tab2, tab3, tab4 = st.tabs(
    ["🔍 সিলেক্টর চেক", "⬇️ স্ক্র্যাপ", "📊 টপিক বিশ্লেষণ", "💾 এক্সপোর্ট"]
)

# ---------------- ট্যাব ১: সিলেক্টর ডিবাগ ----------------
with tab1:
    st.subheader("প্রথমেই এটা চালাও")
    st.write("একটা পেজ এনে দেখাবে কোন CSS সিলেক্টরে কয়টা প্রশ্ন ধরা পড়ছে। "
             "যেটায় ১৫ (বা কাছাকাছি) দেখাবে, সেটাই সাইডবারে বসাও।")

    if st.button("পেজ চেক করো", type="primary"):
        url = sc.build_url(exam, subject or None, 1)
        st.code(url, language=None)
        try:
            with st.spinner("লোড হচ্ছে..."):
                soup = sc.fetch(url, delay=0)
            st.session_state["_soup_ok"] = True

            st.dataframe(pd.DataFrame(sc.probe_selectors(soup)),
                         use_container_width=True, hide_index=True)

            subs = sc.get_subjects(soup)
            if subs:
                st.subheader("সাবজেক্ট তালিকা")
                st.dataframe(pd.DataFrame(subs),
                             use_container_width=True, hide_index=True)

            st.info(f"মোট পেজ: {sc.get_total_pages(soup)}")

            sample = sc.parse_page(soup, selector or None)
            st.subheader(f"অটো-পার্স ফলাফল: {len(sample)}টি প্রশ্ন")
            if sample:
                st.json(sample[0])
        except Exception as e:
            st.error(f"ব্যর্থ: {e}")

# ---------------- ট্যাব ২: স্ক্র্যাপ ----------------
with tab2:
    st.subheader("ডেটা সংগ্রহ")
    est = (end_page - start_page + 1) * delay
    st.caption(f"আনুমানিক সময়: ~{est/60:.1f} মিনিট")

    if st.button("স্ক্র্যাপ শুরু করো", type="primary"):
        bar = st.progress(0.0)
        status = st.empty()
        collected, failed = [], []
        total = end_page - start_page + 1

        for i, page in enumerate(range(int(start_page), int(end_page) + 1)):
            url = sc.build_url(exam, subject or None, page)
            status.write(f"পেজ {page} — সংগ্রহ হয়েছে {len(collected)}টি")
            try:
                soup = sc.fetch(url, delay=delay)
                collected += sc.parse_page(soup, selector or None)
            except Exception as e:
                failed.append(f"পেজ {page}: {e}")
            bar.progress((i + 1) / total)

        st.session_state.questions += collected
        status.empty()
        st.success(f"এই রানে {len(collected)}টি — মোট জমা {len(st.session_state.questions)}টি")
        if failed:
            with st.expander(f"{len(failed)}টি পেজ ব্যর্থ"):
                st.write("\n".join(failed))

    if st.session_state.questions:
        st.divider()
        df = pd.DataFrame(st.session_state.questions)
        st.dataframe(df.head(50), use_container_width=True)

# ---------------- ট্যাব ৩: টপিক বিশ্লেষণ ----------------
with tab3:
    st.subheader("কোন পাঠ আগে লিখবে")
    if not st.session_state.questions:
        st.info("আগে কিছু ডেটা স্ক্র্যাপ করো।")
    else:
        topics = [q["topic"] for q in st.session_state.questions if q.get("topic")]
        if not topics:
            st.warning("কোনো টপিক ট্যাগ পাওয়া যায়নি — সিলেক্টর ঠিক আছে কিনা দেখো।")
        else:
            counts = Counter(topics)
            tdf = pd.DataFrame(counts.most_common(), columns=["টপিক", "প্রশ্ন"])
            tdf["শতাংশ"] = (tdf["প্রশ্ন"] / len(topics) * 100).round(1)
            tdf["ক্রমযোগ %"] = tdf["শতাংশ"].cumsum().round(1)

            c1, c2, c3 = st.columns(3)
            c1.metric("মোট প্রশ্ন", len(st.session_state.questions))
            c2.metric("আলাদা টপিক", len(counts))
            n80 = int((tdf["ক্রমযোগ %"] <= 80).sum()) + 1
            c3.metric("৮০% কভার করতে পাঠ লাগবে", n80)

            st.dataframe(tdf, use_container_width=True, hide_index=True)
            st.bar_chart(tdf.head(25).set_index("টপিক")["প্রশ্ন"])
            st.success(f"শুরু করো উপরের {n80}টি টপিক দিয়ে — এতেই ৮০% প্রশ্ন কভার হবে।")

# ---------------- ট্যাব ৪: এক্সপোর্ট ----------------
with tab4:
    if not st.session_state.questions:
        st.info("এখনো কোনো ডেটা নেই।")
    else:
        qs = st.session_state.questions
        st.write(f"মোট {len(qs)}টি প্রশ্ন")

        c1, c2, c3 = st.columns(3)
        c1.download_button(
            "⬇️ JSON",
            json.dumps(qs, ensure_ascii=False, indent=2),
            file_name=f"{exam}_questions.json",
            mime="application/json",
        )

        flat = [{**q, "options": " | ".join(q.get("options", [])),
                 "tags": " > ".join(q.get("tags", []))} for q in qs]
        c2.download_button(
            "⬇️ CSV",
            pd.DataFrame(flat).to_csv(index=False).encode("utf-8-sig"),
            file_name=f"{exam}_questions.csv",
            mime="text/csv",
        )

        # পাঠ লেখার টেমপ্লেট — টপিক ধরে গ্রুপ করা
        lessons = {}
        for q in qs:
            t = q.get("topic") or "অশ্রেণীবদ্ধ"
            lessons.setdefault(t, {
                "lesson_id": t, "title": t,
                "concept": "", "why": "", "mnemonic": "",
                "questions": [],
            })["questions"].append(q)
        c3.download_button(
            "⬇️ পাঠ টেমপ্লেট",
            json.dumps(list(lessons.values()), ensure_ascii=False, indent=2),
            file_name=f"{exam}_lessons.json",
            mime="application/json",
        )
        st.caption("পাঠ টেমপ্লেট = টপিক ধরে গ্রুপ করা প্রশ্ন, concept/why/mnemonic ফাঁকা — "
                   "PDF থেকে পড়ে ওগুলো ভরবে।")
