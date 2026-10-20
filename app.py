import streamlit as st
import pandas as pd
from sqlalchemy import text

st.set_page_config(page_title="Brain Calibration Terminal", layout="wide")

# ---------------------------------------------------------------
# LOGIN GATE
# ---------------------------------------------------------------
if not st.user.is_logged_in:
    st.title("🎯 Brain Calibration & Predictive Tracker")
    st.write("Log in with Google to open your personal forecast log.")
    st.button("Log in with Google", on_click=st.login)
    st.stop()

email = (st.user.email or "").lower()

# Optional invite-only mode: add allowed_emails = ["a@gmail.com", ...] to secrets.
# If that key isn't set, any Google account can log in (each with their own data).
allowed = st.secrets.get("allowed_emails", None)
if allowed and email not in [str(e).lower() for e in allowed]:
    st.title("🎯 Brain Calibration & Predictive Tracker")
    st.error("This Google account isn't authorized to use this app.")
    st.button("Log out", on_click=st.logout)
    st.stop()

# ---------------------------------------------------------------
# DATABASE (Supabase Postgres, every query filtered by user email)
# ---------------------------------------------------------------
conn = st.connection("supabase", type="sql")


def load_predictions() -> pd.DataFrame:
    df = conn.query(
        """
        SELECT id, created_on, question, forecast, outcome, brier_score
        FROM predictions
        WHERE user_email = :email
        ORDER BY id
        """,
        params={"email": email},
        ttl=0,
    )
    df["n"] = range(1, len(df) + 1)  # per-user display number (#1, #2, ...)
    return df


def add_prediction(question: str, forecast: float) -> None:
    with conn.session as s:
        s.execute(
            text(
                """
                INSERT INTO predictions (user_email, question, forecast)
                VALUES (:email, :question, :forecast)
                """
            ),
            {
                "email": email,
                "question": question,
                "forecast": float(forecast),
            },
        )
        s.commit()


def resolve_prediction(pred_id, forecast, outcome: float) -> None:
    score = round((float(forecast) - float(outcome)) ** 2, 4)
    with conn.session as s:
        s.execute(
            text(
                """
                UPDATE predictions
                SET outcome = :outcome, brier_score = :score
                WHERE id = :id AND user_email = :email
                """
            ),
            {
                "outcome": float(outcome),
                "score": score,
                "id": int(pred_id),
                "email": email,
            },
        )
        s.commit()


# ---------------------------------------------------------------
# PAGE HEADER
# ---------------------------------------------------------------
st.title("🎯 Brain Calibration & Predictive Tracker")

# Create tabs for clean navigation
tab1, tab2, tab3 = st.tabs(
    ["📝 Add Forecast", "⚖️ Resolve Outcomes", "📊 Performance Dashboard"]
)

# ---------------------------------------------------------------
# TAB 1: ADD PREDICTIONS
# ---------------------------------------------------------------
with tab1:
    st.header("Log a New Prediction")
    with st.form("pred_form", clear_on_submit=True):
        question = st.text_input(
            "What is the exact Yes/No Question?",
            placeholder="e.g., Will Brent Crude close above $91.50 today?",
        )
        prob = st.slider("Your Assured Probability (%)", min_value=1, max_value=99, value=50)
        submit = st.form_submit_button("Commit Forecast to Database")

        if submit:
            if question.strip():
                add_prediction(question.strip(), prob / 100.0)
                st.success("Forecast logged!")
            else:
                st.warning("Please enter a question before committing.")

# Load this user's data AFTER tab 1 may have added a row, so tabs 2 and 3 are current
df = load_predictions()

# ---------------------------------------------------------------
# SIDEBAR: ACCOUNT + EXPORT
# ---------------------------------------------------------------
with st.sidebar:
    st.header("👤 Account")
    st.caption(f"Signed in as {email}")
    st.button("Log out", on_click=st.logout)

    st.divider()
    st.subheader("Export")
    if df.empty:
        st.caption("Nothing to export yet.")
    else:
        st.download_button(
            "⬇️ Download my data (CSV)",
            data=df.drop(columns=["n"]).to_csv(index=False),
            file_name="brier_forecasts.csv",
            mime="text/csv",
        )

# ---------------------------------------------------------------
# TAB 2: RESOLVE PREDICTIONS
# ---------------------------------------------------------------
with tab2:
    st.header("Resolve Closed Events")
    pending = df[df["outcome"].isna()]

    if pending.empty:
        st.info("All logged forecasts are currently resolved. Great job keeping up!")
    else:
        for row in pending.itertuples():
            label = (
                f"#{row.n} - {row.question} "
                f"(Your Guess: {round(row.forecast * 100)}%)"
            )
            with st.expander(label):
                col1, col2 = st.columns(2)
                if col1.button("Mark as YES (Happened)", key=f"yes_{row.id}"):
                    resolve_prediction(row.id, row.forecast, 1.0)
                    st.rerun()
                if col2.button("Mark as NO (Did Not Happen)", key=f"no_{row.id}"):
                    resolve_prediction(row.id, row.forecast, 0.0)
                    st.rerun()

# ---------------------------------------------------------------
# TAB 3: ANALYTICS DASHBOARD
# ---------------------------------------------------------------
with tab3:
    st.header("Your Calibration Metrics")
    resolved = df[df["brier_score"].notna()]

    if resolved.empty:
        st.warning("No data points available yet. Resolve closed wagers to see your statistics live.")
    else:
        avg_brier = round(float(resolved["brier_score"].mean()), 4)

        # Core metric cards
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Settled Forecasts", len(resolved))
        col2.metric(
            "Overall Brier Score",
            avg_brier,
            help="0.0 is perfect clairvoyance, 0.25 is random chance.",
        )

        if avg_brier <= 0.15:
            status, color = "Elite Superforecaster 🎯", "green"
        elif avg_brier <= 0.24:
            status, color = "Sharp Predictor (+EV Edge) 📈", "blue"
        elif abs(avg_brier - 0.25) < 0.02:
            status, color = "Baseline Guessing (Coin-Flip) 🎲", "orange"
        else:
            status, color = "Overconfident / High Systemic Bias ⚠️", "red"

        col3.markdown(f"**Skill Status:**\n### :{color}[{status}]")

        # Interactive data table
        st.subheader("Historical Log")
        table = pd.DataFrame(
            {
                "#": resolved["n"],
                "Date": resolved["created_on"],
                "Question": resolved["question"],
                "Confidence": (resolved["forecast"] * 100).round().astype(int).astype(str) + "%",
                "Outcome": resolved["outcome"].apply(lambda x: "YES" if x == 1.0 else "NO"),
                "Brier Score": resolved["brier_score"],
            }
        )
        st.dataframe(table, width="stretch", hide_index=True)
