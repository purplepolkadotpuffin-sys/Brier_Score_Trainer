import json
import os
from datetime import datetime

DB_FILE = "brier_tracker_db.json"

def load_db():
    if not os.path.exists(DB_FILE):
        return {"predictions": []}
    with open(DB_FILE, "r") as f:
        return json.load(f)

def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)

def calculate_brier(forecast, outcome):
    # Formula: (Forecast - Outcome)^2
    return round((forecast - outcome) ** 2, 4)

def add_prediction():
    db = load_db()
    print("\n--- Add New Forecast ---")
    market = input("Enter Market (e.g., WTA Tennis, CS2, Brent Crude, Trump): ").strip()
    question = input("Enter Yes/No Question: ").strip()
    
    while True:
        try:
            prob = float(input("Enter your probability percentage (1-99): "))
            if 1 <= prob <= 99:
                forecast_val = prob / 100.0
                break
            print("Please enter a value strictly between 1 and 99.")
        except ValueError:
            print("Invalid input. Enter a number.")

    prediction = {
        "id": len(db["predictions"]) + 1,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "market": market,
        "question": question,
        "forecast": forecast_val,
        "outcome": None,
        "brier_score": None
    }
    
    db["predictions"].append(prediction)
    save_db(db)
    print(f"Prediction safely logged with ID #{prediction['id']}!")

def resolve_prediction():
    db = load_db()
    pending = [p for p in db["predictions"] if p["outcome"] is None]
    
    if not pending:
        print("\nNo pending predictions to resolve.")
        return

    print("\n--- Pending Predictions ---")
    for p in pending:
        print(f"ID #{p['id']} [{p['market']}]: {p['question']} (Your Guess: {int(p['forecast']*100)}%)")
        
    while True:
        try:
            pid = int(input("\nEnter the ID to resolve: "))
            target = next((p for p in pending if p["id"] == pid), None)
            if target:
                break
            print("Invalid ID or prediction already resolved.")
        except ValueError:
            print("Enter a valid number.")

    while True:
        outcome_input = input("Did it happen? (Y/N): ").strip().upper()
        if outcome_input in ['Y', 'N']:
            outcome_val = 1.0 if outcome_input == 'Y' else 0.0
            break
        print("Please enter Y or N.")

    for p in db["predictions"]:
        if p["id"] == pid:
            p["outcome"] = outcome_val
            p["brier_score"] = calculate_brier(p["forecast"], outcome_val)
            print(f"Resolved! Brier Score penalty for this event: {p['brier_score']}")
            break

    save_db(db)

def view_dashboard():
    db = load_db()
    resolved = [p for p in db["predictions"] if p["brier_score"] is not None]
    
    if not resolved:
        print("\nNo resolved forecasts yet. Keep training your brain to build baseline data!")
        return

    total_score = sum(p["brier_score"] for p in resolved)
    avg_brier = round(total_score / len(resolved), 4)
    
    print("\n==============================================")
    print("         FORECASTING ACCURACY DASHBOARD        ")
    print("==============================================")
    print(f" Total Closed Forecasts : {len(resolved)}")
    print(f" Overall Brier Score    : {avg_brier}")
    
    # Evaluate score
    if avg_brier <= 0.15:
        status = "Elite Superforecaster 🎯"
    elif avg_brier <= 0.24:
        status = "Sharp Predictor (Profitable Edge) 📈"
    elif abs(avg_brier - 0.25) < 0.01:
        status = "Baseline Chance (Coin Flip) 🎲"
    else:
        status = "Overconfident / Systemic Bias Present ⚠️"
        
    print(f" Skill Level Status     : {status}")
    print("----------------------------------------------")
    print(f"{'ID':<4}{'Market':<15}{'Forecast':<10}{'Outcome':<10}{'Brier'}")
    for p in resolved:
        print(f"{p['id']:<4}{p['market'][:13]:<15}{int(p['forecast']*100)}%{'':<5}{int(p['outcome']):<10}{p['brier_score']}")
    print("==============================================")

def main():
    while True:
        print("\n=== BRAIN CALIBRATION TERMINAL ===")
        print("1. Add a New Forecast")
        print("2. Resolve a Closed Outcome")
        print("3. View Accuracy Dashboard")
        print("4. Exit")
        choice = input("Select an option (1-4): ").strip()
        
        if choice == "1": add_prediction()
        elif choice == "2": resolve_prediction()
        elif choice == "3": view_dashboard()
        elif choice == "4": break
        else: print("Invalid choice.")

if __name__ == "__main__":
    main()
