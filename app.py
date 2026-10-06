import hashlib
import json
import time
import re
import os
import csv
import yfinance as yf
from flask import Flask, render_template, request, jsonify, session, Response

# Optional: Google GenAI SDK
try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

app = Flask(__name__)
app.secret_key = "omnivest_ai_driven_planner_2026"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

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
        csv.writer(f).writerow(row_data)

    user_csv = get_user_csv_filename(username)
    file_exists = os.path.exists(user_csv)
    with open(user_csv, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
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
# AI ESTIMATION & ADAPTIVE ALLOCATION
# ==========================================
def call_ai_financial_planner(intent_text, tenure_years, mode, budget_or_corpus):
    """
    Asks Gemini AI to analyze any global destination, determine realistic costs,
    and dynamically assign an asset allocation (crypto, stocks, gold, etc.).
    """
    if not (GENAI_AVAILABLE and GEMINI_API_KEY):
        return None

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = f"""
You are an expert financial planning AI. Analyze the user's travel and savings goal:
User Query: "{intent_text}"
Mode: {mode} (goal = user stated destination/trip, budget = user has monthly budget, corpus = fixed payout)
Provided Value: {budget_or_corpus}
Tenure in Years: {tenure_years}

Tasks:
1. If mode is 'goal', estimate realistic expenses:
   - Identify destination country/city and trip duration (days).
   - Estimate flights + total daily accommodation/food.
   - Adjust for 4% yearly inflation over {tenure_years} years + a 10% safety buffer.
   - Output estimated final target corpus in USD.
2. If mode is 'budget', use the provided monthly budget to estimate the final maturity value.
3. If mode is 'corpus', target that exact corpus.
4. Dynamically allocate asset weights based on tenure:
   - For short tenures (< 2 yrs), assign LOW crypto (0-5%) to prevent volatility risk.
   - For long tenures (>= 3 yrs), allocate 10-25% crypto for growth.
   - Ensure pct values of Stock_Market_Index, Mutual_Funds, Real_Estate_REITs, Gold_Precious_Metals, Cryptocurrency_BTC SUM EXACTLY TO 100.

Return strictly raw JSON format (no markdown fences, no backticks) with keys:
{{
  "destination_title": "string",
  "target_corpus": number,
  "ai_rationale": "string explanation of pricing and allocation",
  "risk_profile": "Conservative / Moderate / Aggressive High-Yield",
  "allocation_pcts": {{
     "Stock_Market_Index": number,
     "Mutual_Funds": number,
     "Real_Estate_REITs": number,
     "Gold_Precious_Metals": number,
     "Cryptocurrency_BTC": number
  }}
}}
"""
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"AI Model Error: {e}")
        return None

# ==========================================
# API ROUTES
# ==========================================
@app.route('/api/market-prices', methods=['GET'])
def get_market_prices():
    tickers = {
        "Bitcoin (BTC)": "BTC-USD",
        "S&P 500": "^GSPC",
        "Gold": "GC=F",
        "Real Estate": "VNQ"
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
                live_data[name] = {"price": 100.0, "change": 0.0, "status": "up"}
        except Exception:
            live_data[name] = {"price": 100.0, "change": 0.0, "status": "up"}
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

@app.route('/api/analyze', methods=['POST'])
def analyze():
    if 'user' not in session: return jsonify({"status": "error"}), 401
    data = request.json or {}
    
    mode = data.get('mode', 'goal')
    years = max(int(data.get('years', 3)), 1)
    statement = data.get('statement', '').strip()
    input_val = float(data.get('input_val', 0) or 0)

    # 1. Try AI-powered calculation
    ai_result = call_ai_financial_planner(statement, years, mode, input_val)

    if ai_result:
        goal_title = ai_result.get("destination_title", statement)
        target_corpus = float(ai_result.get("target_corpus", 5000))
        ai_rationale = ai_result.get("ai_rationale", "AI calculated based on destination costs and duration.")
        risk_profile = ai_result.get("risk_profile", "AI Optimized Strategy")
        allocation = ai_result.get("allocation_pcts", {})
    else:
        # 2. Smart Math Fallback if no AI API key is configured
        goal_title = statement if statement else "Custom Savings Goal"
        if mode == 'goal':
            # Relative heuristic if AI is offline
            is_budget_dest = any(c in statement.lower() for c in ["nepal", "vietnam", "thailand", "india", "sri lanka"])
            base = 1200 if is_budget_dest else 4500
            target_corpus = round(base * ((1.04) ** years) * 1.15, 2)
        elif mode == 'budget':
            target_corpus = round(max(input_val, 500) * 12 * years * 1.35, 2)
        else:
            target_corpus = max(input_val, 3000)
            
        ai_rationale = f"Calculated using travel inflation models and {years}-year compounding."
        risk_profile = "Balanced Compound Growth"
        
        # Tenure-adaptive crypto allocation
        crypto_pct = 5.0 if years <= 1 else (15.0 if years <= 3 else 25.0)
        allocation = {
            "Stock_Market_Index": 40.0,
            "Cryptocurrency_BTC": crypto_pct,
            "Mutual_Funds": 20.0 - (crypto_pct - 5.0),
            "Real_Estate_REITs": 20.0,
            "Gold_Precious_Metals": 15.0
        }

    # Compute Monthly SIP based on 14.5% compound rate
    expected_rate = 0.145
    r = expected_rate / 12
    n = years * 12
    monthly_sip = round(target_corpus / ( (((1 + r)**n - 1) / r) * (1 + r) ), 2)
    total_invested = round(monthly_sip * n, 2)

    cagr_map = {
        "Stock_Market_Index": 15.0,
        "Cryptocurrency_BTC": 22.0,
        "Mutual_Funds": 12.5,
        "Real_Estate_REITs": 11.0,
        "Gold_Precious_Metals": 9.5
    }

    portfolio_detailed = {}
    for asset, pct in allocation.items():
        pct_val = float(pct)
        allocated_principal = round(total_invested * (pct_val / 100.0), 2)
        cagr = cagr_map.get(asset, 12.0)
        projected_return = round(allocated_principal * ((1 + (cagr/100.0)) ** years), 2)
        portfolio_detailed[asset] = {
            "pct": pct_val,
            "amount": allocated_principal,
            "projected_return": projected_return,
            "cagr": f"{cagr}%"
        }

    return jsonify({
        "status": "success",
        "data": {
            "goal_identified": goal_title,
            "risk_profile": risk_profile,
            "tenure_years": years,
            "monthly_allocation": monthly_sip,
            "target_savings_goal": target_corpus,
            "expected_rate_annual": f"{expected_rate * 100:.1f}%",
            "total_principal_invested": total_invested,
            "estimated_maturity_value": target_corpus,
            "estimated_profit": round(target_corpus - total_invested, 2),
            "portfolio_breakdown": portfolio_detailed,
            "ai_rationale": ai_rationale
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

    csv_file = GLOBAL_CSV_FILE if is_admin else get_user_csv_filename(u)
    filename = "global_master_investments.csv" if is_admin else f"{u}_investment_portfolio.csv"

    if os.path.exists(csv_file):
        with open(csv_file, "r", encoding="utf-8") as f:
            content = f.read()
        return Response(content, mimetype="text/csv", headers={"Content-Disposition": f"attachment;filename={filename}"})
    return jsonify({"status": "error", "message": "No CSV records found."}), 404

if __name__ == '__main__':
    app.run(debug=True, port=5000)
