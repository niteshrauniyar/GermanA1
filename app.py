"""
Goethe A1 German Exam Practice App — Streamlit
Fixes from JSX version:
  1. examCount passed directly (not from stale state) so each paper is truly new
  2. Proper page flow: generate → exam → results → generate again (no stuck state)
"""

import json
import re
import anthropic
import streamlit as st

# ─── Anthropic client ────────────────────────────────────────────────────────
client = anthropic.Anthropic()   # reads ANTHROPIC_API_KEY from env

# ─── Prompts ─────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a Goethe-Institut A1 German exam generator. Generate a complete A1 exam in JSON.
Follow this EXACT structure (same as official Goethe A1 "Start Deutsch 1"):

{
  "lesen": {
    "teil1": [
      { "id":1, "text":"<short German notice/sign/label, 1-3 sentences>", "statement":"<a claim about the text in German>", "answer":"richtig|falsch" }
      ... 5 items
    ],
    "teil2": [
      { "id":1, "sign":"<short German sign text>", "question":"<question in German>", "options":["a)...","b)...","c)..."], "answer":"a|b|c" }
      ... 4 items
    ],
    "teil3": [
      { "id":1, "message":"<short informal German message/ad/notice 2-4 sentences>", "question":"<question in German>", "options":["a)...","b)...","c)..."], "answer":"a|b|c" }
      ... 5 items
    ]
  },
  "hoeren": {
    "teil1": [
      { "id":1, "transcript":"<short German dialogue 3-5 lines, label speakers as Person A/B>", "question":"<question in German>", "options":["a)...","b)...","c)..."], "answer":"a|b|c" }
      ... 4 items
    ],
    "teil2": [
      { "id":1, "transcript":"<announcement or message in German 2-4 sentences>", "statement":"<claim about the announcement in German>", "answer":"richtig|falsch" }
      ... 5 items
    ]
  },
  "schreiben": {
    "teil1": {
      "instruction": "Füllen Sie das Formular aus. (Fill in the form.)",
      "context": "<scenario in German, e.g. registering at a sports club>",
      "fields": ["Vorname","Nachname","Alter","Land","Telefonnummer","E-Mail","Hobbys"],
      "sampleAnswers": { "Vorname":"Maria", "Nachname":"Müller", "Alter":"28", "Land":"Spanien", "Telefonnummer":"0176 1234567", "E-Mail":"maria@email.de", "Hobbys":"Lesen, Schwimmen" }
    },
    "teil2": {
      "instruction": "Schreiben Sie eine kurze Nachricht (ca. 30 Wörter). (Write a short message, about 30 words.)",
      "prompt": "<specific task in German>",
      "keyPoints": ["<point 1 in English>","<point 2 in English>","<point 3 in English>"]
    }
  }
}

IMPORTANT:
- All German text must be authentic A1 level (simple vocabulary, present tense, familiar topics)
- Vary topics across the exam: don't repeat the same scenario
- Return ONLY valid JSON, no markdown, no extra text
- Make the exam feel like a real Goethe exam paper"""


# ─── API helpers ─────────────────────────────────────────────────────────────
def generate_exam(paper_number: int) -> dict:
    """Call Claude to generate a fresh exam. paper_number is passed directly — no stale state."""
    msg = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": (
                f"Generate exam paper #{paper_number}. "
                "Use different topics, vocabulary, and scenarios from previous papers. "
                "Return only valid JSON."
            )
        }]
    )
    raw = "".join(b.text for b in msg.content if hasattr(b, "text"))
    clean = re.sub(r"```json|```", "", raw).strip()
    return json.loads(clean)


def ai_check_writing(prompt: str, key_points: list[str], student_text: str) -> dict:
    msg = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=400,
        messages=[{
            "role": "user",
            "content": f"""You are a Goethe A1 German exam examiner. Evaluate this student writing task.

Task: {prompt}
Key points required: {', '.join(key_points)}

Student's answer: "{student_text}"

Respond ONLY in this JSON format (no markdown):
{{
  "score": <0-100>,
  "grade": "<A1 Pass / A1 Fail>",
  "feedback": "<2-3 sentences in English>",
  "corrections": ["<correction 1>","<correction 2>"],
  "missing": ["<missing point if any>"]
}}"""
        }]
    )
    raw = "".join(b.text for b in msg.content if hasattr(b, "text"))
    clean = re.sub(r"```json|```", "", raw).strip()
    return json.loads(clean)


# ─── Session state init ───────────────────────────────────────────────────────
def init_state():
    defaults = {
        "page": "welcome",      # welcome | exam | results
        "exam": None,
        "exam_count": 0,
        "answers": {},
        "section": 0,           # 0=Lesen 1=Hören 2=Schreiben
        "submitted": False,
        "scores": None,
        "ai_score": None,
        "error": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def reset_for_new_exam():
    st.session_state.answers = {}
    st.session_state.submitted = False
    st.session_state.scores = None
    st.session_state.ai_score = None
    st.session_state.section = 0
    st.session_state.error = None


# ─── UI helpers ──────────────────────────────────────────────────────────────
def section_header(title: str, subtitle: str, color: str):
    st.markdown(f"<h2 style='color:{color};margin-bottom:2px'>{title}</h2>", unsafe_allow_html=True)
    st.caption(subtitle)


def result_badge(selected, correct, show):
    if not show:
        return ""
    if selected == correct:
        return " ✅"
    return " ❌"


# ─── Sections ────────────────────────────────────────────────────────────────
def render_lesen(exam, answers, show_results):
    section_header("📖 Lesen", "Reading · 14 questions · 3 parts", "#e8c547")

    # Teil 1
    st.markdown("#### Teil 1 — Richtig oder Falsch? (5 items)")
    st.caption("Lesen Sie die Texte. Sind die Aussagen richtig oder falsch?")
    for i, item in enumerate(exam["lesen"]["teil1"]):
        key = f"l1_{i}"
        with st.container(border=True):
            st.markdown(f"**{i+1}.** {item['text']}")
            st.markdown(f"*Aussage:* {item['statement']}")
            opts = ["richtig", "falsch"]
            current = answers.get(key)
            idx = opts.index(current) if current in opts else None
            choice = st.radio(
                f"l1_{i}_radio", opts,
                index=idx, horizontal=True,
                label_visibility="collapsed",
                key=f"radio_l1_{i}",
                disabled=show_results
            )
            if not show_results and choice != current:
                st.session_state.answers[key] = choice
                st.rerun()
            if show_results:
                correct = item["answer"]
                if answers.get(key) == correct:
                    st.success(f"✓ Correct — {correct}")
                else:
                    st.error(f"✗ Correct answer: {correct}")

    # Teil 2
    st.markdown("#### Teil 2 — Schilder (4 items, Multiple Choice)")
    for i, item in enumerate(exam["lesen"]["teil2"]):
        key = f"l2_{i}"
        with st.container(border=True):
            st.markdown(f"**{i+1}.** 🪧 *{item['sign']}*")
            st.markdown(f"**{item['question']}**")
            opts = item["options"]
            current = answers.get(key)
            letters = [o[0] for o in opts]
            idx = letters.index(current) if current in letters else None
            choice = st.radio(
                f"l2_{i}_radio", opts,
                index=idx, key=f"radio_l2_{i}",
                label_visibility="collapsed",
                disabled=show_results
            )
            if not show_results and choice:
                letter = choice[0]
                if letter != current:
                    st.session_state.answers[key] = letter
                    st.rerun()
            if show_results:
                correct = item["answer"]
                user = answers.get(key, "—")
                if user == correct:
                    st.success(f"✓ Correct — {correct}")
                else:
                    st.error(f"✗ Your answer: {user} | Correct: {correct}")

    # Teil 3
    st.markdown("#### Teil 3 — Kurze Texte (5 items, Multiple Choice)")
    for i, item in enumerate(exam["lesen"]["teil3"]):
        key = f"l3_{i}"
        with st.container(border=True):
            st.info(item["message"])
            st.markdown(f"**{item['question']}**")
            opts = item["options"]
            current = answers.get(key)
            letters = [o[0] for o in opts]
            idx = letters.index(current) if current in letters else None
            choice = st.radio(
                f"l3_{i}_radio", opts,
                index=idx, key=f"radio_l3_{i}",
                label_visibility="collapsed",
                disabled=show_results
            )
            if not show_results and choice:
                letter = choice[0]
                if letter != current:
                    st.session_state.answers[key] = letter
                    st.rerun()
            if show_results:
                correct = item["answer"]
                user = answers.get(key, "—")
                if user == correct:
                    st.success(f"✓ Correct — {correct}")
                else:
                    st.error(f"✗ Your answer: {user} | Correct: {correct}")


def render_hoeren(exam, answers, show_results):
    section_header("🔊 Hören", "Listening · 9 questions · 2 parts", "#5b8dee")
    st.info("💡 Audio transcripts are shown as text. In the real exam you would listen to recordings.")

    # Teil 1
    st.markdown("#### Teil 1 — Gespräche (4 items, Multiple Choice)")
    for i, item in enumerate(exam["hoeren"]["teil1"]):
        key = f"h1_{i}"
        with st.container(border=True):
            with st.expander(f"🔊 Dialogue {i+1} — click to read transcript"):
                st.markdown(item["transcript"])
            st.markdown(f"**{item['question']}**")
            opts = item["options"]
            current = answers.get(key)
            letters = [o[0] for o in opts]
            idx = letters.index(current) if current in letters else None
            choice = st.radio(
                f"h1_{i}_radio", opts,
                index=idx, key=f"radio_h1_{i}",
                label_visibility="collapsed",
                disabled=show_results
            )
            if not show_results and choice:
                letter = choice[0]
                if letter != current:
                    st.session_state.answers[key] = letter
                    st.rerun()
            if show_results:
                correct = item["answer"]
                user = answers.get(key, "—")
                if user == correct:
                    st.success(f"✓ Correct — {correct}")
                else:
                    st.error(f"✗ Your answer: {user} | Correct: {correct}")

    # Teil 2
    st.markdown("#### Teil 2 — Ansagen — Richtig oder Falsch? (5 items)")
    st.caption("Hören Sie die Ansagen. Sind die Aussagen richtig oder falsch?")
    for i, item in enumerate(exam["hoeren"]["teil2"]):
        key = f"h2_{i}"
        with st.container(border=True):
            with st.expander(f"🔊 Announcement {i+1}"):
                st.markdown(item["transcript"])
            st.markdown(f"*Aussage:* {item['statement']}")
            opts = ["richtig", "falsch"]
            current = answers.get(key)
            idx = opts.index(current) if current in opts else None
            choice = st.radio(
                f"h2_{i}_radio", opts,
                index=idx, horizontal=True,
                key=f"radio_h2_{i}",
                label_visibility="collapsed",
                disabled=show_results
            )
            if not show_results and choice != current:
                st.session_state.answers[key] = choice
                st.rerun()
            if show_results:
                correct = item["answer"]
                if answers.get(key) == correct:
                    st.success(f"✓ Correct — {correct}")
                else:
                    st.error(f"✗ Correct answer: {correct}")


def render_schreiben(exam, answers, show_results):
    section_header("✍️ Schreiben", "Writing · 2 parts · AI-graded", "#47c98e")
    schreiben = exam["schreiben"]

    # Teil 1 — Form
    st.markdown("#### Teil 1 — Formular ausfüllen")
    with st.container(border=True):
        st.caption(schreiben["teil1"]["instruction"])
        st.markdown(f"*{schreiben['teil1']['context']}*")
        cols = st.columns(2)
        for j, field in enumerate(schreiben["teil1"]["fields"]):
            fkey = f"s1_{field}"
            with cols[j % 2]:
                val = st.text_input(
                    field, value=answers.get(fkey, ""),
                    key=f"input_{fkey}", disabled=show_results
                )
                if not show_results:
                    st.session_state.answers[fkey] = val
                if show_results:
                    st.caption(f"Beispiel: {schreiben['teil1']['sampleAnswers'].get(field, '—')}")

    # Teil 2 — Message
    st.markdown("#### Teil 2 — Kurze Nachricht schreiben")
    with st.container(border=True):
        st.caption(schreiben["teil2"]["instruction"])
        st.markdown(f"**{schreiben['teil2']['prompt']}**")
        st.markdown("**Key points to include:**")
        for kp in schreiben["teil2"]["keyPoints"]:
            st.markdown(f"- {kp}")

        msg_text = st.text_area(
            "Your message", value=answers.get("s2_message", ""),
            height=150, key="s2_textarea",
            placeholder="Schreiben Sie hier Ihre Nachricht... (Write your message here...)",
            disabled=show_results
        )
        if not show_results:
            st.session_state.answers["s2_message"] = msg_text

        words = len(msg_text.strip().split()) if msg_text.strip() else 0
        color = "green" if 20 <= words <= 40 else "red"
        st.markdown(f":{color}[{words} Wörter — aim: ~30 words]")

        if not show_results and st.button("🤖 AI Check Writing", disabled=not msg_text.strip()):
            with st.spinner("Evaluating your writing…"):
                try:
                    result = ai_check_writing(
                        schreiben["teil2"]["prompt"],
                        schreiben["teil2"]["keyPoints"],
                        msg_text
                    )
                    st.session_state.ai_score = result
                    st.rerun()
                except Exception as e:
                    st.error(f"Evaluation failed: {e}")

        if st.session_state.ai_score:
            ai = st.session_state.ai_score
            passed = ai["score"] >= 60
            col1, col2 = st.columns([1, 3])
            with col1:
                if passed:
                    st.success(f"**{ai['score']}%**\n\n{ai['grade']}")
                else:
                    st.error(f"**{ai['score']}%**\n\n{ai['grade']}")
            with col2:
                st.markdown(ai["feedback"])
                if ai.get("corrections"):
                    st.markdown("**Corrections:**")
                    for c in ai["corrections"]:
                        st.markdown(f"- {c}")
                if ai.get("missing"):
                    st.markdown("**Missing points:**")
                    for m in ai["missing"]:
                        st.markdown(f"- {m}")


# ─── Score calculator ─────────────────────────────────────────────────────────
def calculate_scores(exam, answers) -> dict:
    correct = total = 0
    breakdown = {}

    # Lesen
    l_correct = 0
    for i, item in enumerate(exam["lesen"]["teil1"]):
        total += 1
        if answers.get(f"l1_{i}") == item["answer"]:
            correct += 1; l_correct += 1
    for i, item in enumerate(exam["lesen"]["teil2"]):
        total += 1
        if answers.get(f"l2_{i}") == item["answer"]:
            correct += 1; l_correct += 1
    for i, item in enumerate(exam["lesen"]["teil3"]):
        total += 1
        if answers.get(f"l3_{i}") == item["answer"]:
            correct += 1; l_correct += 1
    breakdown["Lesen"] = (l_correct, 14)

    # Hören
    h_correct = 0
    for i, item in enumerate(exam["hoeren"]["teil1"]):
        total += 1
        if answers.get(f"h1_{i}") == item["answer"]:
            correct += 1; h_correct += 1
    for i, item in enumerate(exam["hoeren"]["teil2"]):
        total += 1
        if answers.get(f"h2_{i}") == item["answer"]:
            correct += 1; h_correct += 1
    breakdown["Hören"] = (h_correct, 9)

    return {"correct": correct, "total": total, "breakdown": breakdown}


# ─── Pages ────────────────────────────────────────────────────────────────────
def page_welcome():
    st.markdown("<h1 style='text-align:center'>🇩🇪 Goethe A1</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align:center;color:gray'>Start Deutsch 1 — Practice Exam</h3>", unsafe_allow_html=True)
    st.divider()

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("**📖 Lesen (Reading)**\n\n3 parts · 14 questions\nSigns, notices, messages")
    with col2:
        st.markdown("**🔊 Hören (Listening)**\n\n2 parts · 9 questions\nDialogues, announcements")
    with col3:
        st.markdown("**✍️ Schreiben (Writing)**\n\n2 parts\nForm + short message (AI-graded)")

    st.divider()
    st.caption("🤖 Unlimited unique exams generated by AI · Passing score: 60%")

    if st.button("🚀 Start Exam Paper 1", type="primary", use_container_width=True):
        _do_generate()


def _do_generate():
    """Generate a new exam and navigate to exam page. Uses a local counter to avoid stale state."""
    reset_for_new_exam()
    next_count = st.session_state.exam_count + 1   # ← FIX: compute locally, not from state
    with st.spinner(f"Generating exam paper #{next_count}…"):
        try:
            exam = generate_exam(next_count)
            st.session_state.exam = exam
            st.session_state.exam_count = next_count   # update after success
            st.session_state.page = "exam"
            st.rerun()
        except Exception as e:
            st.session_state.error = f"Failed to generate exam: {e}"
            st.rerun()


def page_exam():
    exam = st.session_state.exam
    answers = st.session_state.answers
    show_results = st.session_state.submitted
    section = st.session_state.section

    # Top bar
    c1, c2, c3 = st.columns([2, 3, 2])
    with c1:
        st.markdown(f"**🇩🇪 Goethe A1** · Paper #{st.session_state.exam_count}")
    with c2:
        tabs = ["📖 Lesen", "🔊 Hören", "✍️ Schreiben"]
        chosen = st.radio("section_nav", tabs, index=section, horizontal=True, label_visibility="collapsed")
        new_section = tabs.index(chosen)
        if new_section != section:
            st.session_state.section = new_section
            st.rerun()
    with c3:
        if st.button("New Paper 🔄", use_container_width=True):
            _do_generate()

    st.divider()

    if section == 0:
        render_lesen(exam, answers, show_results)
    elif section == 1:
        render_hoeren(exam, answers, show_results)
    else:
        render_schreiben(exam, answers, show_results)

    st.divider()
    col_prev, col_next, col_submit = st.columns([1, 1, 2])
    with col_prev:
        if section > 0:
            if st.button(f"← {['Lesen','Hören'][section-1]}"):
                st.session_state.section = section - 1
                st.rerun()
    with col_next:
        if section < 2:
            if st.button(f"{['Hören','Schreiben'][section]} →"):
                st.session_state.section = section + 1
                st.rerun()
    with col_submit:
        if not show_results:
            if st.button("✓ Submit Exam", type="primary", use_container_width=True):
                st.session_state.scores = calculate_scores(exam, answers)
                st.session_state.submitted = True
                st.session_state.page = "results"
                st.rerun()
        else:
            if st.button("📊 View Results", type="primary", use_container_width=True):
                st.session_state.page = "results"
                st.rerun()


def page_results():
    scores = st.session_state.scores
    pct = round((scores["correct"] / scores["total"]) * 100)
    passed = pct >= 60

    st.markdown(f"<h2 style='text-align:center'>{'✅ Bestanden (Passed)' if passed else '❌ Nicht bestanden (Not passed)'}</h2>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Score", f"{pct}%", f"{scores['correct']}/{scores['total']} correct")
    with col2:
        lc, lt = scores["breakdown"]["Lesen"]
        st.metric("📖 Lesen", f"{lc}/{lt}")
    with col3:
        hc, ht = scores["breakdown"]["Hören"]
        st.metric("🔊 Hören", f"{hc}/{ht}")

    if st.session_state.ai_score:
        ai = st.session_state.ai_score
        st.metric("✍️ Schreiben (AI)", f"{ai['score']}%", ai["grade"])

    st.divider()
    col_review, col_new = st.columns(2)
    with col_review:
        if st.button("🔍 Review Answers", use_container_width=True):
            st.session_state.page = "exam"
            st.rerun()
    with col_new:
        if st.button(f"🚀 New Exam Paper #{st.session_state.exam_count + 1}", type="primary", use_container_width=True):
            _do_generate()   # ← FIX: always generates fresh content with correct number


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    st.set_page_config(
        page_title="Goethe A1 German Exam",
        page_icon="🇩🇪",
        layout="wide"
    )
    init_state()

    if st.session_state.error:
        st.error(st.session_state.error)
        if st.button("Try Again"):
            st.session_state.error = None
            st.rerun()
        return

    page = st.session_state.page
    if page == "welcome":
        page_welcome()
    elif page == "exam":
        page_exam()
    elif page == "results":
        page_results()


if __name__ == "__main__":
    main()
