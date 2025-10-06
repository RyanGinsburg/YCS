# Run:
#   pip install streamlit pandas
#   streamlit run app.py

from __future__ import annotations
import datetime as dt, json, os, random, re, unicodedata
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
import pandas as pd
import streamlit as st
import html

QUESTION_FILE = "question_bank.json"
DEMO_DATE = dt.date(2025, 10, 5)  # locked demo date

UNIT_NAME = "October: Money Basics"
PRIMARY = "#22c55e"   # green
PRIMARY_DARK = "#16a34a"
BG = "#f8fafc"
CARD = "#ffffff"
BORDER = "#e5e7eb"
MUTED = "#6b7280"
ACCENT = "#0ea5e9"
AMBER = "#f59e0b"

# Scoring knobs
POINTS_CORRECT = 10
POINTS_CORRECT_HINT = 5
POINTS_PERFECT_BONUS = 20
PROGRESS_FINISH_PER_Q = 6 #bonus

st.set_page_config(page_title="Daily Finance Challenge", layout="wide")

st.markdown(f"""
<style>
:root{{
  --green:{PRIMARY}; --green-600:{PRIMARY_DARK}; --green-100:#dcfce7;
  --muted:{MUTED}; --bg:{BG}; --card:{CARD}; --border:{BORDER}; --accent:{ACCENT};
  --amber:{AMBER};
}}
html, body, [data-testid="stAppViewContainer"]{{ background: var(--bg); }}
.block-container{{ padding-top:1.0rem; padding-bottom:2rem; }}
.header-band{{
  background:linear-gradient(90deg, var(--green) 0%, #a7f3d0 100%);
  border-radius:14px; padding:18px 20px; color:#063d22;
}}
.header-band h1, .header-band h3, .header-band p{{ margin:0; color:#063d22; }}
.card{{ background:var(--card); border:1px solid var(--border); border-radius:14px; padding:16px 18px; }}
.meta-pill{{
  display:inline-block; padding:4px 10px; border-radius:999px; background:var(--green-100);
  color:#065f46; font-size:12px; margin-right:8px; border:1px solid #bbf7d0;
}}
.combo-pill{{
  display:inline-block; padding:4px 10px; border-radius:999px; background:#fef3c7;
  color:#92400e; font-size:12px; border:1px solid #fde68a; margin-left:8px;
}}
.stButton>button{{ border-radius:12px; border:1px solid var(--border); background:#fff; color:#0b0f10; }}
.stButton>button:hover{{ border-color:var(--green); background:#f8fff9; }}
.stButton>button[kind="primary"]{{ background:#fff !important; color:#0b0f10 !important; }}

.progress-wrap{{ background:var(--card); border:1px solid var(--border); border-radius:14px; padding:12px 16px; }}
.progress-label{{ font-size:13px; color:var(--muted); }}

.hint-btn > button{{ background:#f1f5f9 !important; color:#0f172a !important; }}
.submit-btn > button{{ background:{ACCENT} !important; color:#fff !important; border:none; }}
.next-btn > button{{ background:{PRIMARY} !important; color:#fff !important; border:none; }}
.next-btn > button:hover{{ background:{PRIMARY_DARK} !important; }}

.small-muted{{ color:var(--muted); font-size:12px; }}
.stats-band{{ background:#fff; border:1px solid var(--border); border-radius:14px; padding:10px 14px; }}
.tab-title{{ font-weight:600; margin-bottom:0.5rem; }}

/* Global list reset */
ul, ol {{ list-style: none !important; margin: 0 !important; padding-left: 0 !important; }}
li {{ list-style: none !important; }}
li::marker {{ content: "" !important; }}

/* Streamlit markdown container lists */
[data-testid="stMarkdownContainer"] ul,
[data-testid="stMarkdownContainer"] ol {{
  list-style: none !important; margin: 0 !important; padding-left: 0 !important;
}}
[data-testid="stMarkdownContainer"] li::marker {{ content: "" !important; }}

/* Remove metric delta dot/icon */
[data-testid="stMetricDelta"] svg {{ display: none !important; }}

/* Prevent any SVG icon injected into headings */
[data-testid="stMarkdownContainer"] h1 svg,
[data-testid="stMarkdownContainer"] h2 svg,
[data-testid="stMarkdownContainer"] h3 svg,
[data-testid="stMarkdownContainer"] h4 svg,
[data-testid="stMarkdownContainer"] h5 svg,
[data-testid="stMarkdownContainer"] h6 svg {{ display: none !important; }}

.header-band, .header-band * {{ list-style: none !important; }}
h1, h2, h3, h4, h5, h6 {{ list-style-type: none !important; }}
</style>
""", unsafe_allow_html=True)


@dataclass
class QAResult:
    qid: str
    category: str
    correct: bool
    used_hint: bool
    user_answer: str
    explain: str
    seconds: float

@dataclass
class SaveState:
    display_name: str = "You"
    total_points: int = 0
    streak: int = 0
    last_played: Optional[str] = None
    streak_freezes: int = 3
    history: List[Dict[str, Any]] = field(default_factory=list)
    category_stats: Dict[str, Dict[str, int]] = field(default_factory=dict)
    badges: Dict[str, bool] = field(default_factory=dict)
    room_code: Optional[str] = None
    def to_json(self)->str: return json.dumps(asdict(self), indent=2)
    @staticmethod
    def from_json(s: str)->"SaveState": return SaveState(**json.loads(s))

@dataclass
class PlaySession:
    date: dt.date
    questions: List[Dict[str, Any]]
    idx: int = 0
    score_today: int = 0
    results: List[QAResult] = field(default_factory=list)
    answered: bool = False
    used_hint: bool = False
    completed: bool = False
    correct_streak: int = 0
    answered_count: int = 0
    progress_visual: float = 0.0
    start_ts: Optional[dt.datetime] = None
    end_ts: Optional[dt.datetime] = None
    finished_by_progress: bool = False  #check if day was done by progress

#load question bank
def load_bank(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        st.error(f"Question file `{path}` not found."); st.stop()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        months = data.get("months", {})
        return {k.title(): v for k, v in months.items()}
    except Exception as e:
        st.error(f"Failed to parse `{path}`: {e}"); st.stop()

MONTH_BANK = load_bank(QUESTION_FILE)

def get_day_questions(d: dt.date) -> List[Dict[str, Any]]:
    month = d.strftime("%B")   
    day = d.strftime("%d")     
    month_obj = MONTH_BANK.get(month, {})
    days = month_obj.get("days", {})
    qs = days.get(day, [])
    return qs

#clean text
_ZW_CHARS = r"[\u200B-\u200D\uFEFF]"  
_CTRL_CHARS = r"[\u0000-\u001F\u007F]"  

def normalize_unicode(s: str) -> str:
    try:
        return unicodedata.normalize("NFKC", s)
    except Exception:
        return s

def clean_text(s: str) -> str:
    if not isinstance(s, str): return s
    s = normalize_unicode(s)
    s = re.sub(_ZW_CHARS, "", s)
    s = re.sub(_CTRL_CHARS, " ", s)
    s = re.sub(r"\s+", " ", s)          
    s = re.sub(r"\s*,\s*", ", ", s)     
    s = re.sub(r"\s+\.", ".", s)        
    s = s.replace(" ,", ",")            
    return s.strip()

def sanitize_question(q: Dict[str, Any]) -> Dict[str, Any]:
    q = dict(q)  # shallow copy
    if "prompt" in q: q["prompt"] = clean_text(q["prompt"])
    if "choices" in q and isinstance(q["choices"], list):
        q["choices"] = [clean_text(x) for x in q["choices"]]
    if "explain" in q: q["explain"] = clean_text(q["explain"])
    if "answer_text" in q and isinstance(q["answer_text"], str):
        q["answer_text"] = clean_text(q["answer_text"])
    if "answer" in q and isinstance(q["answer"], str):
        q["answer"] = clean_text(q["answer"])
    return q

def norm(s:str)->str: return s.strip().lower()
def check_numeric_text(u_text: str, a: float, t: float) -> bool:
    try:
        if u_text is None: return False
        u_text = u_text.strip()
        if u_text == "": return False
        val = float(u_text.replace(",", ""))  
        return abs(val - float(a)) <= float(t)
    except Exception:
        return False

def check_mc(u:Optional[str], a:str)->bool: return (u or "")==a
def check_tf(u:Optional[str], a:str)->bool: return (u or "")==a
def check_fib(u:str, a:str)->bool: return norm(u)==norm(a)

#states
def get_save()->SaveState:
    if "save" not in st.session_state: st.session_state.save = SaveState()
    return st.session_state.save

def update_streak_with_freeze(save:SaveState, playing_date:dt.date):
    if not save.last_played:
        save.streak = 1
        save.last_played = playing_date.isoformat()
        return
    last = dt.date.fromisoformat(save.last_played)
    delta = (playing_date - last).days
    if delta == 0:
        return
    elif delta == 1:
        save.streak += 1
    elif delta > 1:
        if save.streak_freezes > 0:
            save.streak_freezes -= 1
            save.streak += 1
            st.toast("Streak Freeze used!")
        else:
            save.streak = 1
    save.last_played = playing_date.isoformat()

FAKE_GLOBAL = []
FAKE_CLASSROOMS = {}

def gen_room_code()->str:
    alphabet="ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(random.choice(alphabet) for _ in range(6))

def class_roster_for(code:str)->List[Dict[str,Any]]:
    return []

def render_leaderboard(title:str, rows:List[Dict[str,Any]]):
    if not rows:
        st.markdown(f"### 🏆 {title}")
        st.info("No entries yet. Play today to appear on the leaderboard!")
        return
    df=pd.DataFrame(rows).sort_values(by=["score","time"], ascending=[False,True]).reset_index(drop=True)
    df.index=df.index+1
    st.markdown(f"### 🏆 {title}")
    st.dataframe(
        df.rename(columns={"name":"Name","score":"Score","time":"Time (s)"}),
        use_container_width=True, hide_index=False,
        column_config={"Time (s)": st.column_config.NumberColumn(format="%d")}
    )


save = get_save()
colL,colR=st.columns([2,1], gap="large")
with colL:
    st.markdown("<div class='header-band'>", unsafe_allow_html=True)
    st.markdown(f"#### Unit: {UNIT_NAME}")
    st.markdown("### Daily Finance Challenge")
    st.markdown("Daily sets that ramp from intro → advanced across each month’s unit.")
    st.markdown("</div>", unsafe_allow_html=True)
with colR:
    st.markdown("<div class='stats-band'>", unsafe_allow_html=True)
    st.caption("Today")
    st.write(f" **{DEMO_DATE.strftime('%B %d, %Y')}**")
    c1,c2 = st.columns(2)
    c1.metric("Total Points", save.total_points)
    c2.metric("Streak", save.streak or 0)
    st.markdown("</div>", unsafe_allow_html=True)

def get_session() -> PlaySession:
    if "play" not in st.session_state:
        qs = [sanitize_question(q) for q in get_day_questions(DEMO_DATE)]
        if not qs:
            st.error(f"No questions found for {DEMO_DATE.strftime('%B %d')} in `{QUESTION_FILE}`.")
            st.stop()
        st.session_state.play = PlaySession(date=DEMO_DATE, questions=qs)
    return st.session_state.play

play = get_session()

tab_daily, tab_leader, tab_groups, tab_profile = st.tabs(
    ["Daily Questions", "🏆 Leaderboards", "👥 Groups", "👤 Profile"]
)

with tab_daily:
    m1,m2,m3,m4=st.columns(4)
    m1.metric("Question", f"{min(play.idx+1, len(play.questions))} / {len(play.questions)}")
    m2.metric("Score (Today)", play.score_today)
    m3.metric("Streak", save.streak or 0)
    m4.metric("Combo", f"{play.correct_streak}x")

    progress_pct=int(min(100, round(play.progress_visual*100)))
    st.markdown("<div class='progress-wrap'>", unsafe_allow_html=True)
    st.markdown("<span class='progress-label'>Progress</span>", unsafe_allow_html=True)
    st.progress(progress_pct); st.markdown("</div>", unsafe_allow_html=True)
    st.write("")

    def add_cat_stat(cat:str, correct:bool):
        d=save.category_stats.setdefault(cat, {"correct":0,"attempted":0})
        d["attempted"]+=1
        if correct: d["correct"]+=1

    HINTS={
        "budget":"50/30/20 is a useful guide.",
        "paycheck":"Net = gross - withholdings.",
        "credit":"Utilization = balance ÷ limit × 100.",
        "saving":"Compounding grows with time.",
        "investing":"Diversify to spread risk.",
        "loans":"Principal = amount borrowed.",
        "scams":"Verify via official channels you initiate.",
        "insurance":"Deductible = amount you pay first."
    }

    def finish_day_by_progress_if_needed():
        if not play.completed and play.progress_visual >= 1.0:
            remaining = max(0, len(play.questions) - play.answered_count)
            bonus = remaining * PROGRESS_FINISH_PER_Q
            if bonus > 0:
                play.score_today += bonus
                st.toast(f"Progress maxed! Early finish bonus: +{bonus}", icon="✨")
            play.finished_by_progress = True
            play.completed = True
            play.end_ts = dt.datetime.now()
            st.balloons()
            st.rerun()

    if play.completed:
        correct_count=sum(1 for r in play.results if r.correct)
        total_time=int((play.end_ts - play.start_ts).total_seconds()) if (play.start_ts and play.end_ts) else 0
        end_reason = " (progress finish)" if getattr(play, "finished_by_progress", False) else ""
        st.success(f"Daily set complete{end_reason}!")
        st.subheader(f"Score: {play.score_today}  •  Correct: {correct_count}/{len(play.questions)}  •  Time: {total_time}s")

        if st.session_state.get("recorded_today") != play.date.isoformat():
            update_streak_with_freeze(save, play.date)
            for r in play.results: add_cat_stat(r.category, r.correct)

            if (not play.finished_by_progress) and correct_count==len(play.questions):
                play.score_today += POINTS_PERFECT_BONUS
                save.badges["perfect_day"]=True
                st.toast(f"Perfect Day! +{POINTS_PERFECT_BONUS} bonus")
            if save.streak>=5: save.badges["streak_5"]=True
            if save.streak>=10: save.badges["streak_10"]=True
            if play.score_today>=100: save.badges["centurion"]=True

            save.total_points += play.score_today
            save.history.append({
                "date":play.date.isoformat(),"score":play.score_today,"time":total_time,
                "correct":correct_count,"total":len(play.questions),
                "finished_by_progress": play.finished_by_progress,
                "categories":[r.category for r in play.results]
            })
            st.session_state["recorded_today"] = play.date.isoformat()

        for r in play.results:
            icon="Correct" if r.correct else "Incorrect"
            with st.expander(f"{icon} [{r.category}] {r.qid} • Your answer: {r.user_answer} • {int(r.seconds)}s"):
                st.markdown(r.explain)

        st.info("See the **Leaderboards** tab to compare your score and time.")

        if st.button("Replay Today"):
            st.session_state.play = PlaySession(date=DEMO_DATE, questions=[sanitize_question(q) for q in get_day_questions(DEMO_DATE)])
            st.rerun()

    else:
        q_raw = play.questions[play.idx]
        q = sanitize_question(q_raw)

        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown(f"<span class='meta-pill'>Unit: {UNIT_NAME}</span>", unsafe_allow_html=True)
        st.markdown(f"<div class='small-muted'>Category: {q['category'].title()}</div>", unsafe_allow_html=True)
        st.markdown(f"<h3>Q{play.idx+1}. {html.escape(q['prompt'])}</h3>", unsafe_allow_html=True)
        if play.start_ts is None: play.start_ts = dt.datetime.now()

        submitted=False; got_right=False; user_ans=""; q_start=dt.datetime.now()

        if q["type"]=="mc":
            choice=st.radio("Choose one:", q["choices"], index=None, key=f"mc_{q['id']}")
            c1, c2 = st.columns([1,1])
            with c1:
                if st.button("Hint", key=f"hint_{play.idx}", use_container_width=True):
                    if not play.answered:
                        st.info(HINTS.get(q["category"], "Think it through carefully.")); play.used_hint=True
            with c2:
                if st.button("Submit", key=f"submit_{play.idx}", use_container_width=True, help="Check your answer"):
                    if not play.answered and choice is not None:
                        got_right=check_mc(choice, q["answer"]); user_ans=str(choice); submitted=True

        elif q["type"]=="numeric":
            num_text = st.text_input("Enter a number:", value="", placeholder="e.g., 1200 or 12.5")
            c1, c2 = st.columns([1,1])
            with c1:
                if st.button("Hint", key=f"hint_{play.idx}", use_container_width=True):
                    if not play.answered:
                        st.info(HINTS.get(q["category"], "Think it through carefully.")); play.used_hint=True
            with c2:
                if st.button("Submit", key=f"submit_{play.idx}", use_container_width=True):
                    if not play.answered:
                        tol = q.get("tolerance", 0.0)
                        got_right = check_numeric_text(num_text, q["answer_num"], tol)
                        user_ans = num_text.strip()
                        if user_ans == "":
                            st.error("Please enter a number before submitting.")
                        else:
                            submitted = True

        elif q["type"]=="truefalse":
            tf=st.radio("True or False", ["True","False"], index=None, key=f"tf_{q['id']}")
            c1, c2 = st.columns([1,1])
            with c1:
                if st.button("Hint", key=f"hint_{play.idx}", use_container_width=True):
                    if not play.answered:
                        st.info(HINTS.get(q["category"], "Think it through carefully.")); play.used_hint=True
            with c2:
                if st.button("Submit", key=f"submit_{play.idx}", use_container_width=True):
                    if not play.answered and tf is not None:
                        got_right=check_tf(tf, q["answer"]); user_ans=str(tf); submitted=True

        elif q["type"]=="fib":
            text=st.text_input("Type your answer:", value="", placeholder="Type a single word or short phrase", key=f"fib_{q['id']}")
            c1, c2 = st.columns([1,1])
            with c1:
                if st.button("Hint", key=f"hint_{play.idx}", use_container_width=True):
                    if not play.answered:
                        st.info(HINTS.get(q["category"], "Think it through carefully.")); play.used_hint=True
            with c2:
                if st.button("Submit", key=f"submit_{play.idx}", use_container_width=True):
                    if not play.answered and text.strip():
                        got_right=check_fib(text, q["answer_text"]); user_ans=text.strip(); submitted=True
                    elif not play.answered:
                        st.error("Please enter an answer before submitting.")

        # After submit
        if submitted and not play.answered:
            q_time=(dt.datetime.now()-q_start).total_seconds()
            if got_right and not play.used_hint:
                play.score_today += POINTS_CORRECT; st.success(f"Correct! +{POINTS_CORRECT}")
            elif got_right and play.used_hint:
                play.score_today += POINTS_CORRECT_HINT; st.success(f"Correct (with hint)! +{POINTS_CORRECT_HINT}")
            else:
                st.error("Incorrect.")
            st.info(q["explain"])

            play.results.append(QAResult(qid=q["id"], category=q["category"], correct=got_right,
                                         used_hint=(got_right and play.used_hint),
                                         user_answer=user_ans, explain=q["explain"], seconds=q_time))
            play.answered=True; play.answered_count+=1

            # Combo progress bar that speeds up on streaks
            if got_right:
                play.correct_streak += 1
                boost = 1.0 if play.correct_streak==1 else 1.5 if play.correct_streak==2 else 1.8 if play.correct_streak==3 else 2.0
                play.progress_visual = min(1.0, play.progress_visual + (1.0/len(play.questions))*boost)
                st.toast(f"{play.correct_streak} in a row!", icon="")
            else:
                play.correct_streak = 0
                play.progress_visual = min(1.0, play.progress_visual + (1.0/len(play.questions)))

            finish_day_by_progress_if_needed()

        # Click next
        if play.answered and not play.completed:
            next_btn = st.container()
            with next_btn:
                if st.container().button("Next ➡️", key=f"next_{play.idx}", use_container_width=True):
                    play.idx += 1
                    play.answered = False
                    play.used_hint = False
                    if play.idx >= len(play.questions):
                        # Finished by answering all questions
                        if sum(1 for r in play.results if r.correct)==len(play.questions):
                            play.score_today += POINTS_PERFECT_BONUS
                            st.toast(f"Perfect Day! +{POINTS_PERFECT_BONUS} bonus", icon="")
                        play.completed=True; play.end_ts=dt.datetime.now(); st.balloons()
                        st.rerun()
                    else:
                        st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

with tab_leader:
    st.markdown("<p class='tab-title'>Compare with others</p>", unsafe_allow_html=True)
    # If the user already completed, show today's stats summary up top
    if play.completed and play.start_ts and play.end_ts:
        total_time=int((play.end_ts - play.start_ts).total_seconds())
        st.info(f"Your result for {DEMO_DATE.strftime('%b %d, %Y')}: **{play.score_today} pts**, **{total_time}s**")

    global_rows = FAKE_GLOBAL + (
        [{"name":get_save().display_name,"score":play.score_today,"time":
          int((play.end_ts - play.start_ts).total_seconds()) if (play.start_ts and play.end_ts) else 0}]
        if play.completed else []
    )
    render_leaderboard(f"Global — {DEMO_DATE.strftime('%b %d, %Y')}", global_rows)

    if save.room_code:
        class_rows = class_roster_for(save.room_code) + (
            [{"name":save.display_name,"score":play.score_today,"time":
              int((play.end_ts - play.start_ts).total_seconds()) if (play.start_ts and play.end_ts) else 0}]
            if play.completed else []
        )
        render_leaderboard(f"Classroom {save.room_code}", class_rows)
    else:
        st.info("Join or create a classroom in the **Groups** tab to see a classroom leaderboard.")

with tab_groups:
    st.markdown("<p class='tab-title'>Create or join a classroom</p>", unsafe_allow_html=True)
    col1, col2 = st.columns([1,1])
    with col1:
        if st.button("Create Room"):
            save.room_code = gen_room_code()
            st.success(f"Room created: **{save.room_code}**")
    with col2:
        join=st.text_input("Join by code", placeholder="e.g., ECON1A or ABC123")
        if st.button("Join"):
            if join.strip():
                save.room_code=join.strip().upper()
                st.success(f"Joined room **{save.room_code}**")
            else:
                st.error("Enter a code to join.")
    st.caption(f"Current room: **{save.room_code or '—'}**")

# ============================ PROFILE TAB ============================
with tab_profile:
    st.markdown("<p class='tab-title'>Your profile & progress</p>", unsafe_allow_html=True)
    save.display_name = st.text_input("Display name", value=save.display_name, max_chars=20)
    c1,c2,c3 = st.columns(3)
    c1.metric("Total Points", save.total_points)
    c2.metric("Streak", save.streak or 0)
    c3.metric("Streak Freezes", save.streak_freezes)

    st.write("### Category Accuracy")
    if save.category_stats:
        df=pd.DataFrame(save.category_stats).T
        df["accuracy %"]=(df["correct"]/df["attempted"]*100).round(1)
        st.dataframe(df, use_container_width=True)
        st.bar_chart(df["accuracy %"])
    else:
        st.caption("No answers yet.")

    if save.badges:
        st.write("### Badges")
        st.write(" • ".join([k.replace('_',' ').title() for k,v in save.badges.items() if v]))
    else:
        st.caption("Earn badges by playing!")

    st.write("---")
    st.write("### Save / Load")
    st.download_button("Download Save (JSON)", data=save.to_json().encode("utf-8"),
                       file_name="dfc_save.json", mime="application/json")
    up=st.file_uploader("Load Save", type=["json"])
    if up is not None:
        try:
            st.session_state.save=SaveState.from_json(up.read().decode("utf-8"))
            st.success("Save loaded!")
        except:
            st.error("Invalid save file.")
