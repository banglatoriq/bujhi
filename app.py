"""
বুঝি — ডেটা কালেকশন
চালাও:  streamlit run app.py
"""

import json
import os
import sqlite3

import pandas as pd
import streamlit as st

import scraper as sc
import bundle
import targets

DATA_DIR = "data"

st.set_page_config(page_title="বুঝি — ডেটা", page_icon="📚", layout="wide")

# ---------------- state ----------------
for k, v in {"subjects": [], "exam": "bcs-preliminary",
             "selector": "", "log": []}.items():
    st.session_state.setdefault(k, v)


def db_path(exam):
    return os.path.join(DATA_DIR, exam, "bujhi.db")


def raw_path(exam, slug):
    d = os.path.join(DATA_DIR, exam, "raw")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{(slug or 'all').replace('/', '_')[:100]}.json")


def load_raw(exam, slug):
    p = raw_path(exam, slug)
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_raw(exam, slug, questions):
    p = raw_path(exam, slug)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(questions, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


# ---------------- হেডার ----------------
st.title("📚 বুঝি — ডেটা কালেকশন")

with st.expander("🎯 আমার টার্গেট পরীক্ষা (BCS · ব্যাংক · NTRCA · প্রাথমিক)",
                 expanded=True):
    tcol1, tcol2 = st.columns([1, 3])
    group = tcol1.radio("ক্যাটাগরি", list(targets.TARGETS.keys()))
    items = targets.TARGETS[group]
    idx = tcol2.selectbox("পরীক্ষা", range(len(items)),
                          format_func=lambda i: items[i][0])
    if tcol2.button("এই পরীক্ষাটা বাছো", use_container_width=True):
        st.session_state.exam = items[idx][1]
        st.session_state.subjects = []
        st.rerun()
    st.caption(f"slug: `{items[idx][1]}`")

with st.expander("🔎 অন্য পরীক্ষা খুঁজি"):
    if st.button("পরীক্ষার তালিকা আনো"):
        with st.spinner("হোমপেজ থেকে আনা হচ্ছে..."):
            try:
                st.session_state["exam_list"] = sc.get_exams()
            except Exception as e:
                st.error(f"আনা গেল না: {e}")

    if st.session_state.get("exam_list"):
        edf = pd.DataFrame(st.session_state["exam_list"])
        kind = st.radio("ধরন", ["চাকরি", "ভর্তি", "সব"],
                        horizontal=True, index=0)
        if kind != "সব":
            edf = edf[edf["type"] == kind]
        q = st.text_input("নাম দিয়ে খোঁজো", placeholder="যেমন: শিক্ষক")
        if q:
            edf = edf[edf["name"].str.contains(q, case=False, na=False)]
        st.caption(f"{len(edf)}টি পরীক্ষা — slug কলাম থেকে কপি করে নিচে বসাও")
        st.dataframe(edf[["name", "slug", "type"]],
                     use_container_width=True, hide_index=True)

c1, c2, c3 = st.columns([2, 2, 1])
st.session_state.exam = c1.text_input("পরীক্ষা (exam slug)", st.session_state.exam)
st.session_state.selector = c2.text_input(
    "Card CSS selector", st.session_state.selector,
    placeholder="খালি রাখলে অটো-ডিটেক্ট")
c3.write("")
if c3.button("🔄 সাবজেক্ট আনো", type="primary", use_container_width=True):
    with st.spinner("সাইট থেকে সাবজেক্ট তালিকা আনা হচ্ছে..."):
        try:
            soup = sc.fetch(sc.build_url(st.session_state.exam), delay=0)
            subs = sc.get_subjects(soup)
            if not subs:
                subs = [{"name": "সব প্রশ্ন", "slug": None, "count": "?"}]
            st.session_state.subjects = subs
            st.success(f"{len(subs)}টি সাবজেক্ট পাওয়া গেছে")
        except Exception as e:
            st.error(f"আনা গেল না: {e}")

exam = st.session_state.exam

tab_dl, tab_plan, tab_lesson, tab_out = st.tabs(
    ["⬇️ সাবজেক্ট নামাও", "📊 পাঠ পরিকল্পনা", "✍️ পাঠ লেখা", "💾 অ্যাপের ফাইল"])

# ================= ট্যাব ১: নামানো =================
with tab_dl:
    if not st.session_state.subjects:
        st.info("উপরে **🔄 সাবজেক্ট আনো** চাপো।")
    else:
        names = [f"{s['name']}  ({s['count']})" for s in st.session_state.subjects]
        pick = st.selectbox("কোন সাবজেক্ট নামাবে?", range(len(names)),
                            format_func=lambda i: names[i])
        sub = st.session_state.subjects[pick]

        existing = load_raw(exam, sub["slug"])
        a, b = st.columns([1, 3])
        delay = a.slider("বিরতি (সেকেন্ড)", 1.0, 5.0, 2.0, 0.5)
        if existing:
            b.info(f"এই সাবজেক্টের {len(existing)}টি প্রশ্ন আগেই নামানো আছে। "
                   "আবার চালালে বাকিটুকু নামবে।")

        if st.button("⬇️ এই সাবজেক্টের সব প্রশ্ন নামাও",
                     type="primary", use_container_width=True):

            questions = list(existing)
            seen = {q.get("url") for q in questions if q.get("url")}
            done_pages = set()
            sp = raw_path(exam, sub["slug"]) + ".pages"
            if os.path.exists(sp):
                try:
                    done_pages = set(json.load(open(sp)))
                except Exception:
                    pass

            bar = st.progress(0.0)
            status = st.empty()
            metric = st.empty()

            try:
                first = sc.fetch(sc.build_url(exam, sub["slug"], 1), delay=delay)
                total_pages = sc.get_total_pages(first)

                if 1 not in done_pages:
                    for q in sc.parse_page(first, st.session_state.selector or None):
                        if q.get("url") not in seen:
                            seen.add(q.get("url"))
                            questions.append(q)
                    done_pages.add(1)

                todo = [p for p in range(2, total_pages + 1) if p not in done_pages]
                mins = len(todo) * delay / 60
                status.write(f"মোট {total_pages} পেজ · বাকি {len(todo)} · "
                             f"আনুমানিক {mins:.1f} মিনিট")

                empty_streak = 0
                for i, page in enumerate(todo, 1):
                    before = len(questions)
                    try:
                        soup = sc.fetch(sc.build_url(exam, sub["slug"], page),
                                        delay=delay)
                        for q in sc.parse_page(soup, st.session_state.selector or None):
                            if q.get("url") not in seen:
                                seen.add(q.get("url"))
                                questions.append(q)
                        done_pages.add(page)
                    except Exception as e:
                        st.warning(f"পেজ {page} বাদ: {e}")

                    # নতুন কিছু না এলে গোনা — টানা ৩ পেজ খালি মানে পেজিনেশন কাজ করছে না
                    empty_streak = 0 if len(questions) > before else empty_streak + 1
                    if empty_streak >= 3:
                        st.error(
                            "টানা ৩টি পেজ থেকে একটাও নতুন প্রশ্ন আসেনি — "
                            "সাইট `?page=` প্যারামিটার উপেক্ষা করছে, পেজিনেশন "
                            "JavaScript/AJAX দিয়ে হয়। থামানো হলো যাতে সময় নষ্ট না হয়। "
                            "আসল endpoint বের করতে হবে (README দেখো)।")
                        break

                    if i % 5 == 0 or i == len(todo):
                        save_raw(exam, sub["slug"], questions)
                        json.dump(sorted(done_pages), open(sp, "w"))

                    bar.progress(i / max(len(todo), 1))
                    metric.metric("সংগ্রহ হয়েছে", f"{len(questions)}টি প্রশ্ন",
                                  f"পেজ {i}/{len(todo)}")

                save_raw(exam, sub["slug"], questions)
                json.dump(sorted(done_pages), open(sp, "w"))

                bundle.build(db_path(exam), exam, sub["name"],
                             sub["slug"], questions)
                status.empty()
                st.success(f"✅ {sub['name']} — {len(questions)}টি প্রশ্ন "
                           "নামানো ও ডেটাবেসে সেভ হয়েছে")
                st.balloons()

            except Exception as e:
                st.error(f"সমস্যা: {e}")

        if existing:
            st.divider()
            st.caption("নমুনা")
            st.dataframe(pd.DataFrame(existing[:20]), use_container_width=True)

    st.caption("⚠️ নামানোর সময় এই ব্রাউজার ট্যাব খোলা রাখো। "
               "বন্ধ হলে থেমে যাবে, তবে যা নেমেছে তা থাকবে — আবার চালালে "
               "বাকিটুকু নামবে।")

# ================= ট্যাব ২: পাঠ পরিকল্পনা =================
with tab_plan:
    p = db_path(exam)
    if not os.path.exists(p):
        st.info("আগে একটা সাবজেক্ট নামাও।")
    else:
        con = sqlite3.connect(p)
        subs = pd.read_sql("SELECT id, name, question_count FROM subjects", con)
        if subs.empty:
            st.info("ডেটাবেস খালি।")
        else:
            sid = st.selectbox("সাবজেক্ট", subs["id"],
                               format_func=lambda i: subs.set_index("id")
                               .loc[i, "name"])
            tdf = pd.read_sql("""
                SELECT t.priority_rank AS 'ক্রম', t.name AS 'টপিক',
                       t.question_count AS 'প্রশ্ন', t.coverage_pct AS 'শতাংশ',
                       l.status AS 'পাঠ'
                FROM topics t LEFT JOIN lessons l ON l.topic_id = t.id
                WHERE t.subject_id = ? ORDER BY t.priority_rank
            """, con, params=(int(sid),))
            tdf["ক্রমযোগ %"] = tdf["শতাংশ"].cumsum().round(1)

            n80 = int((tdf["ক্রমযোগ %"] <= 80).sum()) + 1
            m1, m2, m3 = st.columns(3)
            m1.metric("মোট টপিক", len(tdf))
            m2.metric("৮০% কভার করতে", f"{n80}টি পাঠ")
            m3.metric("মোট প্রশ্ন", int(tdf["প্রশ্ন"].sum()))

            st.success(f"উপরের **{n80}টি টপিক** দিয়ে শুরু করো — "
                       "এতেই এই সাবজেক্টের ৮০% প্রশ্ন কভার হবে।")
            st.dataframe(tdf, use_container_width=True, hide_index=True)
            st.bar_chart(tdf.head(20).set_index("টপিক")["প্রশ্ন"])
        con.close()

# ================= ট্যাব ৩: পাঠ লেখা =================
with tab_lesson:
    p = db_path(exam)
    if not os.path.exists(p):
        st.info("আগে ডেটা নামাও।")
    else:
        con = sqlite3.connect(p)
        ldf = pd.read_sql("""
            SELECT l.id, l.title, l.status, t.question_count, s.name AS subject
            FROM lessons l
            JOIN topics t ON t.id = l.topic_id
            JOIN subjects s ON s.id = t.subject_id
            ORDER BY t.question_count DESC
        """, con)

        if ldf.empty:
            st.info("কোনো পাঠ নেই।")
        else:
            only_draft = st.checkbox("শুধু বাকি পাঠগুলো", value=True)
            view = ldf[ldf.status == "draft"] if only_draft else ldf
            if view.empty:
                st.success("সব পাঠ লেখা হয়ে গেছে 🎉")
            else:
                lid = st.selectbox(
                    "পাঠ বাছো", view["id"],
                    format_func=lambda i: (
                        f"{ldf.set_index('id').loc[i,'title']} "
                        f"— {ldf.set_index('id').loc[i,'question_count']}টি প্রশ্ন"))

                row = pd.read_sql("SELECT * FROM lessons WHERE id=?",
                                  con, params=(int(lid),)).iloc[0]

                st.caption("PDF থেকে পড়ে নিজের ভাষায় লেখো — কপি কোরো না।")
                hook = st.text_area("কেন এটা পড়ব (hook)", row["hook"], height=68)
                concept = st.text_area("মূল ব্যাখ্যা", row["concept"], height=180)
                why = st.text_area("নিয়মটা কেন এমন", row["why"], height=120)
                examples = st.text_area("উদাহরণ", row["examples"], height=120)
                mnemonic = st.text_area("মনে রাখার কৌশল", row["mnemonic"], height=90)
                mistakes = st.text_area("যেখানে ভুল হয়", row["common_mistakes"],
                                        height=90)
                ref = st.text_input("সূত্র (বই, পরিচ্ছেদ)", row["source_ref"])
                done = st.checkbox("পাঠ সম্পূর্ণ", row["status"] == "done")

                if st.button("💾 সেভ করো", type="primary"):
                    con.execute("""UPDATE lessons SET hook=?, concept=?, why=?,
                                   examples=?, mnemonic=?, common_mistakes=?,
                                   source_ref=?, status=? WHERE id=?""",
                                (hook, concept, why, examples, mnemonic,
                                 mistakes, ref, "done" if done else "draft",
                                 int(lid)))
                    con.commit()
                    st.success("সেভ হয়েছে")

                with st.expander("এই পাঠের প্রশ্নগুলো দেখো"):
                    st.dataframe(pd.read_sql(
                        "SELECT question, opt_a, opt_b, opt_c, opt_d, year "
                        "FROM questions WHERE lesson_id=? LIMIT 100",
                        con, params=(int(lid),)), use_container_width=True)
        con.close()

# ================= ট্যাব ৪: এক্সপোর্ট =================
with tab_out:
    p = db_path(exam)
    if not os.path.exists(p):
        st.info("আগে ডেটা নামাও।")
    else:
        s = bundle.stats(p)
        cols = st.columns(len(s))
        for col, (k, v) in zip(cols, s.items()):
            col.metric(k, v)

        st.divider()
        with open(p, "rb") as f:
            st.download_button("⬇️ bujhi.db (SQLite — Flutter-এ সরাসরি বসাও)",
                               f.read(), file_name="bujhi.db",
                               mime="application/octet-stream",
                               type="primary", use_container_width=True)

        if st.button("JSON হিসেবেও বের করো"):
            files = bundle.export_json(p, os.path.join(DATA_DIR, exam, "json"))
            st.success("তৈরি হয়েছে:")
            for fp in files:
                st.code(fp, language=None)

        st.divider()
        st.markdown("""
**Flutter-এ ব্যবহার**

1. `bujhi.db` রাখো `assets/db/bujhi.db`-তে
2. `pubspec.yaml`-এ assets যোগ করো
3. `sqflite` + `path_provider` দিয়ে প্রথম চালুতে ফাইলটা কপি করে নাও

**টেবিলগুলো:** `subjects` → `topics` → `lessons` → `questions`
প্রতিটি প্রশ্নে `lesson_id` বসানো আছে, তাই পাঠ দেখানোর পর ওই পাঠের
প্রশ্নগুলো টানা সোজা:

```sql
SELECT * FROM questions WHERE lesson_id = ?;
```
""")
