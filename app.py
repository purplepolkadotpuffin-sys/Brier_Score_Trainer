import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime

DB_FILE = "brier_tracker_db.json"

# Page layout configurations
st.set_page_config(page_title="Brain Calibration Terminal", layout="wide")
st.title("🎯 Brain Calibration & Predictive Tracker")
st.write("Train your brain to think in probabilities. Track your performance across WTA, CS2, Oil, and Political Markets.")

# Database functions
def load_db():
    if not os.path.exists(DB_FILE):
        return {"predictions": []}
    with open(DB_FILE, "r") as f:
        return json.load(f)

def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)

db = load_db()

# Create tabs for clean navigation
tab1, tab2, tab3 = st.tabs(["📝 Add Forecast", "⚖️ Resolve Outcomes", "📊 Performance Dashboard"])

# TAB 1: ADD PREDICTIONS
with tab1:
    st.header("Log a New Prediction")
    with st.form("pred_form", clear_on_submit=True):
        market = st.selectbox("Market Category", ["WTA Tennis", "CS2 Esports", "Brent Crude", "Trump Mention Markets", "Other"])
        question = st.text_input("What is the exact Yes/No Question?", placeholder="e.g., Will Brent Crude close above $91.50 today?")
        prob = st.slider("Your Assured Probability (%)", min_value=1, max_value=99, value=50)
        
        submit = st.form_submit_with_button("Commit Forecast to Database")
        if submit and question:
            new_pred = {
                "id": len(db["predictions"]) + 1,
                "date": datetime.now().strftime("%Y-%m-%d"),
                "market": market,
                "question": question,
                "forecast": prob / 100.0,
                "outcome": None,
                "brier_score": None
            }
            db["predictions"].append(new_pred)
            save_db(db)
            st.success(f"Successfully logged Forecast #{new_pred['id']}!")

# TAB 2: RESOLVE PREDICTIONS
with tab2:
    st.header("Resolve Closed Events")
    pending = [p for p in db["predictions"] if p["outcome"] is None]
    
    if not pending:
        st.info("All logged forecasts are currently resolved. Great job keeping up!")
    else:
        for p in pending:
            with st.expander(f"#{p['id']} [{p['market']}] - {p['question']} (Your Guess: {int(p['forecast']*100)}%)"):
                col1, col2 = st.columns(2)
                if col1.button("Mark as YES (Happened)", key=f"yes_{p['id']}"):
                    p["outcome"] = 1.0
                    p["brier_score"] = round((p["forecast"] - 1.0) ** 2, 4)
                    save_db(db)
                    st.rerun()
                if col2.button("Mark as NO (Did Not Happen)", key=f"no_{p['id']}"):
                    p["outcome"] = 0.0
                    p["brier_score"] = round((p["forecast"] - 0.0) ** 2, 4)
                    save_db(db)
                    st.rerun()

# TAB 3: ANALYTICS DASHBOARD
with tab3:
    st.header("Your Calibration Metrics")
    resolved = [p for p in db["predictions"] if p["brier_score"] is not None]
    
    if not resolved:
        st.warning("No data points available yet. Resolve closed wagers to see your statistics live.")
    else:
        df = pd.DataFrame(resolved)
        avg_brier = round(df["brier_score"].mean(), 4)
        
        # Display Core Metrics Cards
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Settled Forecasts", len(resolved))
        col2.metric("Overall Brier Score", avg_brier, help="0.0 is perfect clairvoyance, 0.25 is random chance.")
        
        if avg_brier <= 0.15:
            status, color = "Elite Superforecaster 🎯", "green"
        elif avg_brier <= 0.24:
            status, color = "Sharp Predictor (+EV Edge) 📈", "blue"
        elif abs(avg_brier - 0.25) < 0.02:
            status, color = "Baseline Guessing (Coin-Flip) 🎲", "orange"
        else:
            status, color = "Overconfident / High Systemic Bias ⚠️", "red"
            
        col3.markdown(f"**Skill Status:**\n### :{color}[{status}]")
        
        # Display Interactive Data Table
        st.subheader("Historical Log")
        df["Confidence"] = (df["forecast"] * 100).astype(int).astype(str) + "%"
        df["Outcome Result"] = df["outcome"].apply(lambda x: "YES" if x == 1.0 else "NO")
        st.dataframe(df[["id", "date", "market", "question", "Confidence", "Outcome Result", "brier_score"]], use_container_width=True)
