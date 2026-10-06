import hashlib
import json
import time
import re
import os
import csv
import yfinance as yf
from flask import Flask, render_template, request, jsonify, session, Response

app = Flask(__name__)
app.secret_key = "omnivest_fixdeal_secret_2026"

USERS_FILE = "users.json"
LEDGER_FILE = "ledger.json"
GLOBAL_CSV_FILE = "global_master_investments.csv"

def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r") as f: return json.load(f)
        except Exception: return {}
    return {}

def save_users(users):
    with open(USERS_FILE, "w") as f: json.dump(users, f, indent=4)

def get_user_csv_filename(username):
    safe_user = re.sub(r'[^a-zA-Z0-9_]', '_', username)
    return f"{safe_user}_investment_portfolio.csv"

def ensure_global_csv():
    if not os.path.exists(GLOBAL_CSV_FILE):
        with open(GLOBAL_CSV_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Record_ID", "Timestamp", "User", "Goal_Description",
                "Monthly_SIP", "Target_Corpus", "Tenure_Years", "Projected_Maturity",
                "Stocks_Pct", "Mutual_Funds_Pct", "Real_Estate_Pct", "Gold_Pct", "Crypto_BTC_Pct",
                "Risk_Level"
            ])

def append_to_csvs(username, record_id, timestamp, tx):
    ensure_global_csv()
    pf = tx.get('portfolio', {})
    row_data = [
        record_id,
        time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp)),
        username,
        tx.get('goal'),
        tx.get('monthly_investment'),
        tx.get('target_savings_goal'),
        tx.get('tenure_years'),
        tx.get('target_fund'),
        pf.get('Stock_Market_Index', {}).get('pct', 0),
        pf.get('Mutual_Funds', {}).get('pct', 0),
        pf.get('Real_Estate_REITs', {}).get('pct', 0),
        pf.get('Gold_Precious_Metals', {}).get('pct', 0),
        pf.get('Cryptocurrency_BTC', {}).get('pct', 0),
        tx.get('risk_profile')
    ]

    with open(GLOBAL_CSV_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(row_data)

    user_csv = get_user_csv_filename(username)
    user_file_exists = os.path.exists(user_csv)
    with open(user_csv, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not user_file_exists:
            writer.writerow([
                "Record_ID", "Timestamp", "User", "Goal_Description",
                "Monthly_SIP", "Target_Corpus", "Tenure_Years", "Projected_Maturity",
                "Stocks_Pct", "Mutual_Funds_Pct", "Real_Estate_Pct", "Gold_Pct", "Crypto_BTC_Pct",
                "Risk_Level"
            ])
        writer.writerow(row_data)

def load_ledger():
    if os.path.exists(LEDGER_FILE):
        try:
            with open(LEDGER_FILE, "r") as f: return json.load(f)
        except Exception: return []
    return []

def save_ledger(ledger):
    with open(LEDGER_FILE, "w") as f: json.dump(ledger, f, indent=4)

# ==========================================
# API ENDPOINTS
# ==========================================
@app.route('/api/market-prices', methods=['GET'])
def get_market_prices():
    # Live Yahoo Finance Tickers
    tickers = {
        "Bitcoin (BTC)": "BTC-USD",
        "S&P 500": "^GSPC",
        "Gold": "GC=F",
        "Real Estate (REIT)": "VNQ"
    }
    
    # Accurate fallback prices if network times out
    fallbacks = {
        "Bitcoin (BTC)": {"price": 68450.00, "change": 1.45, "status": "up"},
        "S&P 500": {"price": 5750.25, "change": 0.35, "status": "up"},
        "Gold": {"price": 2650.80, "change": -0.20, "status": "down"},
        "Real Estate (REIT)": {"price": 93.40, "change": 0.15, "status": "up"}
    }

    live_data = {}
    for name, symbol in tickers.items():
        try:
            t = yf.Ticker(symbol)
            df = t.history(period="2d")
            if len(df) >= 1:
                cur = float(df['Close'].iloc[-1])
                prev = float(df['Close'].iloc[-2]) if len(df) >= 2 else cur
                chg = ((cur - prev) / prev) * 100
                live_data[name] = {"price": round(cur, 2), "change": round(chg, 2), "status": "up" if chg >= 0 else "down"}
            else:
                live_data[name] = fallbacks[name]
        except Exception:
            live_data[name] = fallbacks[name]
            
    return jsonify({"status": "success", "market": live_data})

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/auth', methods=['POST'])
def auth():
    data = request.json or {}
    role = data.get('role', 'customer')
    username = data.get('username', '').strip()
    phone = data.get('phone', '').strip()

    if not username or not phone:
        return jsonify({"status": "error", "message": "Username and phone number are required."}), 400

    if role == 'admin':
        if username.lower() == 'admin' and phone == '0000000000':
            session['user'] = 'Admin Master'
            session['is_admin'] = True
            return jsonify({"status": "success", "username": "Admin Master", "is_admin": True})
        else:
            return jsonify({"status": "error", "message": "Invalid Admin credentials. Use admin & 0000000000."}), 401

    users = load_users()
    phone_hash = hashlib.sha256(phone.encode()).hexdigest()

    if username not in users:
        users[username] = {"phone_hash": phone_hash}
        save_users(users)
    elif users[username]["phone_hash"] != phone_hash:
        return jsonify({"status": "error", "message": "Phone number does not match registered username."}), 401

    session['user'] = username
    session['is_admin'] = False
    return jsonify({"status": "success", "username": username, "is_admin": False})

@app.route('/api/logout', methods=['POST'])
def logout():
    session.pop('user', None)
    session.pop('is_admin', None)
    return jsonify({"status": "success"})

@app.route('/api/current-session', methods=['GET'])
def current_session():
    return jsonify({"user": session.get('user'), "is_admin": session.get('is_admin', False)})

def parse_duration_in_days(text):
    # Extracts days, weeks, or months to determine proper stay cost
    text = text.lower()
    days = 7 # Default standard trip length
    
    day_match = re.search(r'(\d+)\s*(?:day|days)', text)
    week_match = re.search(r'(\d+)\s*(?:week|weeks)', text)
    month_match = re.search(r'(\d+)\s*(?:month|months)', text)

    if day_match:
        days = int(day_match.group(1))
    elif week_match:
        days = int(week_match.group(1)) * 7
    elif month_match:
        days = int(month_match.group(1)) * 30

    return max(days, 1)

@app.route('/api/analyze', methods=['POST'])
def analyze():
    if 'user' not in session: return jsonify({"status": "error"}), 401
    data = request.json or {}
    
    mode = data.get('mode', 'goal')
    years = int(data.get('years', 3))
    statement = data.get('statement', '').strip().lower()
    input_val = float(data.get('input_val', 0) or 0)

    # Dynamic destination daily cost engine ($/day living + flights)
    destinations = {
        "italy": {"daily": 180, "flight": 1200},
        "switzerland": {"daily": 260, "flight": 1300},
        "singapore": {"daily": 150, "flight": 600},
        "japan": {"daily": 190, "flight": 1100},
        "dubai": {"daily": 160, "flight": 500},
        "usa": {"daily": 220, "flight": 1400}
    }

    target_corpus = 0
    goal_title = "Custom Wealth Strategy"

    if mode == 'goal':
        matched_dest = None
        for dest, costs in destinations.items():
            if dest in statement:
                matched_dest = dest
                trip_days = parse_duration_in_days(statement)
                raw_trip_cost = costs["flight"] + (costs["daily"] * trip_days)
                # 4% annual inflation over wait years + 15% buffer
                inflated_trip = raw_trip_cost * ((1.04) ** years)
                target_corpus = round(inflated_trip * 1.15, 2)
                goal_title = f"{trip_days}-Day Trip to {dest.capitalize()} (with Buffer)"
                break

        if not matched_dest:
            target_corpus = max(input_val if input_val > 0 else 25000, 5000)
            goal_title = statement if statement else "Custom Savings Target"

        expected_rate = 0.145
        r = expected_rate / 12
        n = years * 12
        monthly_sip = round(target_corpus / ( (((1 + r)**n - 1) / r) * (1 + r) ), 2)
        total_invested = round(monthly_sip * n, 2)

    elif mode == 'budget':
        monthly_sip = max(input_val, 500)
        expected_rate = 0.145
        r = expected_rate / 12
        n = years * 12
        total_invested = round(monthly_sip * n, 2)
        target_corpus = round(monthly_sip * (((1 + r)**n - 1) / r) * (1 + r), 2)
        goal_title = "Monthly SIP Growth Plan"

    else:
        target_corpus = max(input_val, 10000)
        expected_rate = 0.145
        r = expected_rate / 12
        n = years * 12
        monthly_sip = round(target_corpus / ( (((1 + r)**n - 1) / r) * (1 + r) ), 2)
        total_invested = round(monthly_sip * n, 2)
        goal_title = "Fixed Target Builder"

    # Deterministic dynamic allocation matrix
    raw_weights = {
        "Stock_Market_Index": {"pct": 40.0, "cagr": 15.0},
        "Cryptocurrency_BTC": {"pct": 25.0, "cagr": 22.0},
        "Mutual_Funds": {"pct": 15.0, "cagr": 12.5},
        "Real_Estate_REITs": {"pct": 12.0, "cagr": 11.0},
        "Gold_Precious_Metals": {"pct": 8.0, "cagr": 9.5}
    }

    portfolio_detailed = {}
    for asset, details in raw_weights.items():
        allocated_principal = round(total_invested * (details["pct"] / 100.0), 2)
        projected_return = round(allocated_principal * ((1 + (details["cagr"]/100.0)) ** years), 2)
        portfolio_detailed[asset] = {
            "pct": details["pct"],
            "amount": allocated_principal,
            "projected_return": projected_return,
            "cagr": f"{details['cagr']}%"
        }

    return jsonify({
        "status": "success",
        "data": {
            "goal_identified": goal_title,
            "risk_profile": "High-Yield Growth Portfolio",
            "tenure_years": years,
            "monthly_allocation": monthly_sip,
            "target_savings_goal": target_corpus,
            "expected_rate_annual": f"{expected_rate * 100:.1f}%",
            "total_principal_invested": total_invested,
            "estimated_maturity_value": target_corpus,
            "estimated_profit": round(target_corpus - total_invested, 2),
            "portfolio_breakdown": portfolio_detailed,
            "ai_rationale": f"Calculated based on actual stay duration, flights, and 15% contingency buffer over {years} years."
        }
    })

@app.route('/api/execute-investment', methods=['POST'])
def execute():
    if 'user' not in session: return jsonify({"status": "error"}), 401
    data = request.json or {}; plan = data.get('plan', {}); u = session['user']
    
    ledger = load_ledger()
    record_id = len(ledger) + 1
    tx = {
        "record_id": record_id,
        "user": u,
        "goal": plan.get('goal_identified'),
        "monthly_investment": plan.get('monthly_allocation'),
        "target_savings_goal": plan.get('target_savings_goal'),
        "target_fund": plan.get('estimated_maturity_value'),
        "tenure_years": plan.get('tenure_years'),
        "risk_profile": plan.get('risk_profile'),
        "portfolio": plan.get('portfolio_breakdown'),
        "timestamp": time.time()
    }
    ledger.append(tx)
    save_ledger(ledger)
    append_to_csvs(u, record_id, tx["timestamp"], tx)

    return jsonify({"status": "success", "record_id": record_id})

@app.route('/api/my-ledger', methods=['GET'])
def my_ledger():
    if 'user' not in session: return jsonify({"status": "error"}), 401
    u = session['user']
    is_admin = session.get('is_admin', False)
    ledger = load_ledger()
    user_txs = []
    tot_p, tot_m = 0, 0

    for tx in ledger:
        if is_admin or tx.get('user') == u:
            tot_p += float(tx.get('monthly_investment', 0)) * int(tx.get('tenure_years', 5)) * 12
            tot_m += float(tx.get('target_fund', 0))
            user_txs.append({
                "record_id": tx.get("record_id"),
                "timestamp": time.strftime('%d %b %Y, %H:%M', time.localtime(tx.get("timestamp"))),
                "tx": tx
            })

    return jsonify({
        "records": list(reversed(user_txs)),
        "summary": {
            "active_portfolios": len(user_txs),
            "total_principal": round(tot_p, 2),
            "total_projected": round(tot_m, 2),
            "total_gain": round(tot_m - tot_p, 2)
        }
    })

@app.route('/api/export-csv', methods=['GET'])
def export_csv():
    if 'user' not in session: return jsonify({"status": "error"}), 401
    u = session['user']
    is_admin = session.get('is_admin', False)

    if is_admin:
        csv_file = GLOBAL_CSV_FILE
        filename = "global_master_investments.csv"
    else:
        csv_file = get_user_csv_filename(u)
        filename = f"{u}_investment_portfolio.csv"

    if os.path.exists(csv_file):
        with open(csv_file, "r", encoding="utf-8") as f:
            content = f.read()
        return Response(content, mimetype="text/csv", headers={"Content-Disposition": f"attachment;filename={filename}"})
    return jsonify({"status": "error", "message": "No CSV records found."}), 404

if __name__ == '__main__':
    app.run(debug=True, port=5000)
