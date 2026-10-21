import re

import streamlit as st
import pandas as pd
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

st.set_page_config(page_title="Brier Score Trainer", layout="wide")

# ---------------------------------------------------------------
# LOGIN GATE
# ---------------------------------------------------------------
if not st.user.is_logged_in:
    st.title("Brier Score Trainer")
    st.caption("Log probability forecasts, resolve them, and see how well calibrated you are.")
    st.write("Log in with Google to open your personal forecast log.")
    st.button("Log in with Google", on_click=st.login)
    st.stop()

email = (st.user.email or "").lower()

# Optional invite-only mode: add allowed_emails = ["a@gmail.com", ...] to secrets.
# If that key isn't set, any Google account can log in (each with their own data).
allowed = st.secrets.get("allowed_emails", None)
if allowed and email not in [str(e).lower() for e in allowed]:
    st.title("Brier Score Trainer")
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
# LEADERBOARD HELPERS
# ---------------------------------------------------------------
MIN_RESOLVED = 20  # resolved forecasts needed to appear on the leaderboard
NAME_RE = re.compile(r"^[A-Za-z0-9 _.\-]{2,24}$")


def get_display_name():
    names = conn.query(
        "SELECT display_name FROM profiles WHERE user_email = :email",
        params={"email": email},
        ttl=0,
    )
    return names["display_name"].iloc[0] if not names.empty else None


def save_display_name(name: str) -> None:
    with conn.session as s:
        s.execute(
            text(
                """
                INSERT INTO profiles (user_email, display_name)
                VALUES (:email, :name)
                ON CONFLICT (user_email)
                DO UPDATE SET display_name = EXCLUDED.display_name
                """
            ),
            {"email": email, "name": name},
        )
        s.commit()


def try_save_name(candidate: str):
    """Returns an error message, or None if the name was saved."""
    candidate = candidate.strip()
    if not NAME_RE.match(candidate):
        return "Use 2 to 24 letters, numbers, spaces, or _ . - (no @)."
    try:
        save_display_name(candidate)
    except IntegrityError:
        return "That name is taken. Try another."
    return None


def remove_profile() -> None:
    with conn.session as s:
        s.execute(
            text("DELETE FROM profiles WHERE user_email = :email"),
            {"email": email},
        )
        s.commit()


def load_leaderboard() -> pd.DataFrame:
    return conn.query(
        """
        SELECT p.display_name, COUNT(*) AS resolved, AVG(pr.brier_score) AS avg_brier
        FROM predictions pr
        JOIN profiles p ON p.user_email = pr.user_email
        WHERE pr.brier_score IS NOT NULL
        GROUP BY p.display_name
        HAVING COUNT(*) >= :min_n
        ORDER BY avg_brier ASC, resolved DESC
        LIMIT 100
        """,
        params={"min_n": MIN_RESOLVED},
        ttl=0,
    )


# ---------------------------------------------------------------
# PAGE HEADER
# ---------------------------------------------------------------
st.title("Brier Score Trainer")
st.caption("Log probability forecasts, resolve them, and see how well calibrated you are.")

# Create tabs for clean navigation
tab1, tab2, tab3, tab4 = st.tabs(
    ["📝 Add Forecast", "⚖️ Resolve Outcomes", "📊 Performance Dashboard", "🏆 Leaderboard"]
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

# ---------------------------------------------------------------
# TAB 4: GLOBAL LEADERBOARD
# ---------------------------------------------------------------
with tab4:
    st.header("Global Leaderboard")
    st.caption(
        f"Ranked by average Brier score (lower is better). "
        f"You need at least {MIN_RESOLVED} resolved forecasts to appear."
    )

    my_name = get_display_name()
    n_resolved = int(df["brier_score"].notna().sum())

    if my_name is None:
        st.info(
            "Pick a display name to join. Only your name, average score, and number "
            "of resolved forecasts are shown. Your email and forecasts stay private."
        )
        with st.form("join_form"):
            new_name = st.text_input("Display name", max_chars=24, placeholder="e.g., ForecastFox")
            join = st.form_submit_button("Join leaderboard")
        if join:
            err = try_save_name(new_name)
            if err:
                st.error(err)
            else:
                st.rerun()
    else:
        st.write(f"You're on the leaderboard as **{my_name}**.")
        if n_resolved < MIN_RESOLVED:
            st.info(
                f"You have {n_resolved} resolved forecasts. "
                f"{MIN_RESOLVED - n_resolved} more to appear on the board."
            )

    board = load_leaderboard()
    if board.empty:
        st.warning("Nobody has qualified yet.")
    else:
        board.insert(0, "Rank", range(1, len(board) + 1))
        board["avg_brier"] = board["avg_brier"].astype(float).round(4)
        board["Name"] = board["display_name"].where(
            board["display_name"] != my_name, board["display_name"] + " (you)"
        )
        table = board[["Rank", "Name", "avg_brier", "resolved"]].rename(
            columns={"avg_brier": "Avg Brier Score", "resolved": "Resolved"}
        )
        st.dataframe(table, width="stretch", hide_index=True)

    if my_name is not None:
        with st.expander("Change name or leave the leaderboard"):
            with st.form("rename_form"):
                renamed = st.text_input("New display name", value=my_name, max_chars=24)
                rename = st.form_submit_button("Update name")
            if rename:
                err = try_save_name(renamed)
                if err:
                    st.error(err)
                else:
                    st.rerun()
            if st.button("Remove me from the leaderboard"):
                remove_profile()
                st.rerun()
