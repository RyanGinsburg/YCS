# app.py
# ------------------------------------------------------------
# MoneyQuest — Finance Simulator (Single-file Streamlit App)
# ------------------------------------------------------------
# How to run (from your project folder):
#   pip install streamlit pandas
#   streamlit run app.py
#
# NOTE for competitions that restrict AI-generated material:
# Treat this as a starter/teaching template. Rewrite text, tweak logic,
# and add your own features/content before submitting.
# ------------------------------------------------------------

import math
import json
from dataclasses import dataclass, asdict
from typing import List, Dict, Tuple, Optional

import streamlit as st
import pandas as pd


# ----------------------------- UI CONFIG -----------------------------
st.set_page_config(page_title="MoneyQuest", page_icon="💸", layout="centered")


# ----------------------------- DATA MODELS ---------------------------
@dataclass
class MonthlySnapshot:
    month: int
    netWorth: int
    cash: int
    savings: int
    debt: int
    creditScore: int


@dataclass
class Income:
    hoursPerWeek: float = 20.0
    wagePerHour: float = 15.0
    withholdingRate: float = 0.12  # 12% simple educational rate


@dataclass
class PlayerState:
    month: int = 1
    cash: int = 200
    savings: int = 100
    debt: int = 0
    creditScore: int = 680
    income: Income = Income()
    budget_needs: float = 0.5
    budget_wants: float = 0.3
    budget_savings: float = 0.2
    choices: Dict[str, str] = None
    history: List[MonthlySnapshot] = None


# ----------------------------- GAME CONTENT --------------------------
# You can freely edit these to customize costs/prompts/options.
CHOICES: List[Dict] = [
    {
        "id": "phone_plan",
        "title": "Phone Plan",
        "prompt": "Pick a plan for this month.",
        "options": {
            "basic": ("Basic ($30/mo)", 30),
            "standard": ("Standard ($55/mo)", 55),
            "premium": ("Premium ($80/mo)", 80),
        },
    },
    {
        "id": "transit",
        "title": "Getting Around",
        "prompt": "How do you commute?",
        "options": {
            "bus": ("Bus Pass ($50)", 50),
            "rideshare": ("Ride-share (~$120)", 120),
            "bike": ("Bike (maintenance $10)", 10),
        },
    },
    {
        "id": "credit_card",
        "title": "Credit Card Behavior",
        "prompt": "How will you handle your card this month?",
        "options": {
            "pay_full": ("Pay statement in full", 0),
            "min_pay": ("Make only minimum payment", 0),
        },
    },
]


# ----------------------------- ENGINES -------------------------------
def compute_net_pay(hours_per_week: float, wage: float, withholding_rate: float) -> Tuple[float, float, float]:
    """Very simple paycheck calculator (educational)."""
    gross = hours_per_week * wage * 4  # assume 4 weeks per month
    withheld = gross * withholding_rate
    net = gross - withheld
    return round(gross, 2), round(withheld, 2), round(net, 2)


def apply_budget(
    net_income: float,
    needs_p: float,
    wants_p: float,
    savings_p: float,
    fixed_needs_costs: float
) -> Tuple[float, float, float, float]:
    """Allocate income to needs/wants/savings, covering fixed needs first."""
    planned_needs = net_income * needs_p
    planned_wants = net_income * wants_p
    planned_savings = net_income * savings_p

    # Pay fixed needs first
    remaining = max(0.0, net_income - fixed_needs_costs)

    wants_spend = max(0.0, min(planned_wants, remaining - planned_savings))
    savings_add = max(0.0, min(planned_savings, remaining - wants_spend))
    needs_spend = fixed_needs_costs + max(0.0, planned_needs - fixed_needs_costs)
    leftover = max(0.0, remaining - wants_spend - savings_add)

    return (
        round(needs_spend, 2),
        round(wants_spend, 2),
        round(savings_add, 2),
        round(leftover, 2),
    )


def update_credit_score(current: int, utilization: float, on_time_payment: bool) -> int:
    """
    Educational credit score update (NOT FICO).
    Rewards on-time payments and low utilization.
    """
    nxt = current

    # Payment history effect
    nxt += 8 if on_time_payment else -25

    # Utilization (aim <30%)
    if utilization < 0.10:
        nxt += 6
    elif utilization < 0.30:
        nxt += 2
    elif utilization < 0.50:
        nxt -= 6
    else:
        nxt -= 12

    # Clamp to [300, 850]
    return max(300, min(850, int(round(nxt))))


def close_month(
    state: PlayerState,
    fixed_needs_costs: float,
    credit_limit: int = 500
) -> Tuple[MonthlySnapshot, Tuple[float, float, float], Tuple[float, float, float, float]]:
    """
    Run end-of-month updates:
      - compute income & allocations
      - apply simple credit card behavior
      - update cash/savings/debt/score
      - record a MonthlySnapshot
    """
    gross, withheld, net_income = compute_net_pay(
        state.income.hoursPerWeek, state.income.wagePerHour, state.income.withholdingRate
    )

    needs_spend, wants_spend, savings_add, leftover = apply_budget(
        net_income, state.budget_needs, state.budget_wants, state.budget_savings, fixed_needs_costs
    )

    # Credit card: minimal educational model
    min_payment = min(25, state.debt)
    debt_after_interest = math.ceil(state.debt * 1.02)  # 2% monthly interest
    pay_full_choice = (state.choices or {}).get("credit_card") == "pay_full"
    payment = debt_after_interest if pay_full_choice else min_payment
    new_debt = max(0, debt_after_interest - payment)

    # Update balances
    new_cash = round(state.cash + leftover - payment - wants_spend - needs_spend)
    new_savings = round(state.savings + savings_add)

    # Credit score update from utilization + payment history
    utilization = 0 if credit_limit == 0 else (new_debt / credit_limit)
    new_score = update_credit_score(state.creditScore, utilization, payment >= min_payment)

    snapshot = MonthlySnapshot(
        month=state.month,
        netWorth=round(new_cash + new_savings - new_debt),
        cash=new_cash,
        savings=new_savings,
        debt=new_debt,
        creditScore=new_score,
    )

    # Advance
    state.month += 1
    state.cash = new_cash
    state.savings = new_savings
    state.debt = new_debt
    state.creditScore = new_score
    state.history = (state.history or []) + [snapshot]

    return snapshot, (gross, withheld, net_income), (needs_spend, wants_spend, savings_add, leftover)


# ----------------------------- HELPERS -------------------------------
def get_state() -> PlayerState:
    if "state" not in st.session_state:
        st.session_state.state = PlayerState(choices={}, history=[])
    # Ensure choices/history exist
    if st.session_state.state.choices is None:
        st.session_state.state.choices = {}
    if st.session_state.state.history is None:
        st.session_state.state.history = []
    return st.session_state.state


def reset_game() -> None:
    st.session_state.state = PlayerState(choices={}, history=[])


def fixed_needs_from_choices(state: PlayerState) -> float:
    total = 0.0
    for c in CHOICES:
        cid = c["id"]
        chosen = (state.choices or {}).get(cid)
        if chosen and chosen in c["options"]:
            _, cost = c["options"][chosen]
            total += float(cost)
    return round(total, 2)


def export_save(state: PlayerState) -> str:
    """Return a JSON string representing the current save."""
    payload = {
        "state": {
            "month": state.month,
            "cash": state.cash,
            "savings": state.savings,
            "debt": state.debt,
            "creditScore": state.creditScore,
            "income": asdict(state.income),
            "budget_needs": state.budget_needs,
            "budget_wants": state.budget_wants,
            "budget_savings": state.budget_savings,
            "choices": state.choices,
            "history": [asdict(h) for h in (state.history or [])],
        }
    }
    return json.dumps(payload, indent=2)


def import_save(json_str: str) -> Optional[PlayerState]:
    try:
        data = json.loads(json_str)
        s = data.get("state", {})
        inc = s.get("income", {})
        state = PlayerState(
            month=int(s.get("month", 1)),
            cash=int(s.get("cash", 0)),
            savings=int(s.get("savings", 0)),
            debt=int(s.get("debt", 0)),
            creditScore=int(s.get("creditScore", 680)),
            income=Income(
                hoursPerWeek=float(inc.get("hoursPerWeek", 20.0)),
                wagePerHour=float(inc.get("wagePerHour", 15.0)),
                withholdingRate=float(inc.get("withholdingRate", 0.12)),
            ),
            budget_needs=float(s.get("budget_needs", 0.5)),
            budget_wants=float(s.get("budget_wants", 0.3)),
            budget_savings=float(s.get("budget_savings", 0.2)),
            choices=dict(s.get("choices", {})),
            history=[MonthlySnapshot(**h) for h in s.get("history", [])],
        )
        return state
    except Exception:
        return None


# ----------------------------- SIDEBAR -------------------------------
state = get_state()

with st.sidebar:
    st.header("⚙️ Game Controls")
    if st.button("🔄 New Game"):
        reset_game()
        st.success("New game started.")

    st.write("---")
    st.subheader("💾 Save / Load")
    save_json = export_save(state)
    st.download_button(
        "Download Save (JSON)",
        data=save_json.encode("utf-8"),
        file_name="moneyquest_save.json",
        mime="application/json",
    )

    uploaded = st.file_uploader("Load Save", type=["json"])
    if uploaded is not None:
        content = uploaded.read().decode("utf-8", errors="ignore")
        loaded = import_save(content)
        if loaded:
            st.session_state.state = loaded
            st.success("Save loaded!")
        else:
            st.error("Invalid save file.")

    st.write("---")
    st.caption("Educational simulator. Credit logic is simplified; not affiliated with FICO.")


# ----------------------------- MAIN TABS -----------------------------
st.title("💸 MoneyQuest — Finance Simulator (MVP)")

tab_home, tab_paycheck, tab_budget, tab_choices, tab_results = st.tabs(
    ["Home", "Paycheck", "Budget", "Choices", "Results"]
)

# -------- Home --------
with tab_home:
    st.subheader("Welcome")
    st.write(
        "Play one month: get a paycheck, set a budget, make choices, and see how your cash, "
        "savings, debt, and credit score change."
    )
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Month", state.month)
    m2.metric("Cash", f"${state.cash}")
    m3.metric("Savings", f"${state.savings}")
    m4.metric("Debt", f"${state.debt}")
    m5.metric("Credit Score", state.creditScore)

    # History chart
    if state.history:
        hist_df = pd.DataFrame([asdict(h) for h in state.history])
        st.write("**Net Worth & Balances (History)**")
        st.line_chart(hist_df.set_index("month")[["netWorth", "cash", "savings"]])

# -------- Paycheck --------
with tab_paycheck:
    st.subheader("1) Paycheck")
    col1, col2, col3 = st.columns(3)
    state.income.hoursPerWeek = col1.number_input(
        "Hours / Week", min_value=0.0, max_value=80.0, value=float(state.income.hoursPerWeek), step=1.0
    )
    state.income.wagePerHour = col2.number_input(
        "Wage ($/hr)", min_value=0.0, max_value=1000.0, value=float(state.income.wagePerHour), step=0.5
    )
    state.income.withholdingRate = col3.slider(
        "Withholding Rate", min_value=0.0, max_value=0.5, value=float(state.income.withholdingRate), step=0.01
    )

    gross, withheld, net = compute_net_pay(
        state.income.hoursPerWeek, state.income.wagePerHour, state.income.withholdingRate
    )
    st.info(f"Gross: ${gross}  |  Withheld: ${withheld}  |  **Net Pay: ${net}**")

# -------- Budget --------
with tab_budget:
    st.subheader("2) Budget (Needs / Wants / Savings)")
    n = st.slider("Needs %", 0, 100, int(state.budget_needs * 100), 1)
    w = st.slider("Wants %", 0, 100, int(state.budget_wants * 100), 1)
    s = 100 - n - w
    if s < 0:
        st.error("Needs + Wants must be ≤ 100%. Adjust sliders so Savings stays ≥ 0%.")
        # clamp savings to 0 for display; still store a valid value
        s = 0
    state.budget_needs = n / 100
    state.budget_wants = w / 100
    state.budget_savings = s / 100

    # Simple budget bar chart (Streamlit built-in)
    budget_df = pd.DataFrame(
        {
            "Category": ["Needs", "Wants", "Savings"],
            "Percent": [round(state.budget_needs * 100, 1), round(state.budget_wants * 100, 1), round(state.budget_savings * 100, 1)],
        }
    )
    st.write("**Budget Allocation**")
    st.bar_chart(budget_df.set_index("Category"))

# -------- Choices --------
with tab_choices:
    st.subheader("3) Monthly Choices")
    for c in CHOICES:
        st.markdown(f"**{c['title']}** — {c['prompt']}")
        options_keys = list(c["options"].keys())
        labels = [c["options"][k][0] for k in options_keys]

        # Current selection -> index
        current_key = state.choices.get(c["id"])
        default_idx = options_keys.index(current_key) if current_key in options_keys else 0

        chosen_label = st.radio(
            label=c["title"],
            options=labels,
            index=default_idx,
            key=f"radio_{c['id']}",
            horizontal=True,
        )

        # Map label back to option key
        label_to_key = {v[0]: k for k, v in c["options"].items()}
        state.choices[c["id"]] = label_to_key[chosen_label]
        st.write("---")

    st.info(f"Fixed 'needs' cost from choices this month: **${fixed_needs_from_choices(state)}**")

# -------- Results --------
with tab_results:
    st.subheader("4) Results (Close Month)")

    fixed_costs = fixed_needs_from_choices(state)
    gross, withheld, net = compute_net_pay(
        state.income.hoursPerWeek, state.income.wagePerHour, state.income.withholdingRate
    )
    needs_spend, wants_spend, savings_add, leftover = apply_budget(
        net, state.budget_needs, state.budget_wants, state.budget_savings, fixed_costs
    )

    exp_col1, exp_col2 = st.columns(2)
    with exp_col1:
        st.write("**This Month’s Plan (Preview)**")
        st.write(f"- Net income: **${net}**")
        st.write(f"- Needs spend (incl. choices): **${needs_spend}**")
        st.write(f"- Wants spend: **${wants_spend}**")
        st.write(f"- Savings added: **${savings_add}**")
        st.write(f"- Leftover cash: **${leftover}**")

    with exp_col2:
        st.write("**Debt & Credit (Preview)**")
        st.write(f"- Current debt: **${state.debt}**")
        behavior = "Pay in full" if state.choices.get("credit_card") == "pay_full" else "Minimum payment"
        st.write(f"- Credit behavior: **{behavior}**")
        util_preview = 0 if state.debt == 0 else round(min(1.0, state.debt / 500) * 100, 1)
        st.write(f"- Utilization preview (limit $500): **{util_preview}%**")

    if st.button("✅ Close Month"):
        snap, pay_tuple, alloc_tuple = close_month(state, fixed_costs)
        st.success("Month closed! See updated stats below.")
        st.session_state["last_snapshot"] = asdict(snap)

    if "last_snapshot" in st.session_state or state.history:
        last = st.session_state.get("last_snapshot") or asdict(state.history[-1])
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Month Closed", last["month"])
        c2.metric("Cash", f"${last['cash']}")
        c3.metric("Savings", f"${last['savings']}")
        c4.metric("Debt", f"${last['debt']}")
        c5.metric("Credit Score", last["creditScore"])

        # History line chart
        if state.history:
            df_hist = pd.DataFrame([asdict(h) for h in state.history])
            st.write("**Net Worth & Balances (History)**")
            st.line_chart(df_hist.set_index("month")[["netWorth", "cash", "savings"]])

    st.caption("Tip: Try different budgets/choices, then close the month again to compare outcomes.")
