import hashlib
import json
import time
import re
import os
import csv
import yfinance as yf
from flask import Flask, render_template, request, jsonify, session, Response

try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

app = Flask(__name__)
app.secret_key = "omnivest_ai_dynamic_market_2026"

USERS_FILE = "users.json"
LEDGER_FILE = "ledger.json"
GLOBAL_CSV_FILE = "global_master_investments.csv"

# In-memory cache for market tickers to prevent 3-6s yfinance network lag
MARKET_CACHE = {"data": None, "timestamp": 0}
CACHE_TTL = 600  # 10 minutes

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
                "Record_ID", "Timestamp", "User", "Goal_Description", "Budget_Level", "Duration_Days",
                "Monthly_SIP_INR", "Target_Corpus_INR", "Tenure_Years", "Projected_Maturity_INR",
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
        tx.get('travel_style', 'Mid Budget'),
        tx.get('duration_days', 0),
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
                "Record_ID", "Timestamp", "User", "Goal_Description", "Budget_Level", "Duration_Days",
                "Monthly_SIP_INR", "Target_Corpus_INR", "Tenure_Years", "Projected_Maturity_INR",
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

def fetch_live_market_summary():
    global MARKET_CACHE
    now = time.time()
    if MARKET_CACHE["data"] and (now - MARKET_CACHE["timestamp"] < CACHE_TTL):
        return MARKET_CACHE["data"]

    tickers = {
        "Bitcoin": "BTC-INR",
        "NIFTY_50": "^NSEI",
        "Gold": "GC=F",
        "BSE_Sensex": "^BSESN"
    }
    summary = {}
    for name, sym in tickers.items():
        try:
            t = yf.Ticker(sym)
            df = t.history(period="2d")
            if len(df) >= 1:
                cur = float(df['Close'].iloc[-1])
                prev = float(df['Close'].iloc[-2]) if len(df) >= 2 else cur
                chg = round(((cur - prev) / prev) * 100, 2)
                summary[name] = {"price": round(cur, 2), "change_pct": chg}
            else:
                summary[name] = {"price": 0.0, "change_pct": 0.0}
        except Exception:
            summary[name] = {"price": 0.0, "change_pct": 0.0}

    MARKET_CACHE["data"] = summary
    MARKET_CACHE["timestamp"] = now
    return summary

def call_ai_financial_planner_fast(intent_text, tenure_years, mode, budget_or_corpus, budget_level, risk_tier):
    if not GENAI_AVAILABLE:
        return None

    api_key = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()
    if not api_key:
        return None

    try:
        client = genai.Client(api_key=api_key)

        prompt = f"""You are a high-speed financial pricing estimator. All numbers in INR (₹).
User Goal: "{intent_text}"
Tier: {budget_level}
Risk: {risk_tier}
Tenure: {tenure_years} yrs

Calculate:
1. Exact model/trip baseline present cost in INR.
2. Compound at 5% inflation: target_corpus = present_cost * (1.05 ** {tenure_years}).
3. Asset split (sum to 100): Stock_Market_Index, Mutual_Funds, Real_Estate_REITs, Gold_Precious_Metals, Cryptocurrency_BTC.
4. Expected CAGR: 0.08 to 0.16.

Return strictly raw JSON (no markdown):
{{
  "destination_title": "Short title",
  "target_corpus": number,
  "expected_annual_rate": number,
  "ai_rationale": "One brief sentence explaining cost, inflation, and strategy.",
  "allocation_pcts": {{
     "Stock_Market_Index": number,
     "Mutual_Funds": number,
     "Real_Estate_REITs": number,
     "Gold_Precious_Metals": number,
     "Cryptocurrency_BTC": number
  }}
}}"""

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                max_output_tokens=300,
                temperature=0.1
            )
        )

        if not response or not response.text:
            return None

        raw_text = response.text.strip()
        cleaned_text = re.sub(r'^```json\s*', '', raw_text)
        cleaned_text = re.sub(r'\s*```$', '', cleaned_text)
        return json.loads(cleaned_text)

    except Exception as e:
        print(f"[OmniVest Speed Fallback Triggered]: {e}")
        return None

# ==========================================
# API ENDPOINTS
# ==========================================
@app.route('/api/market-prices', methods=['GET'])
def get_market_prices():
    fallbacks = {
        "Bitcoin (BTC)": {"price": 6250000.0, "change": 1.45, "status": "up"},
        "NIFTY 50": {"price": 25200.0, "change": 0.40, "status": "up"},
        "Gold (per 10g)": {"price": 78500.0, "change": -0.25, "status": "down"},
        "BSE SENSEX": {"price": 82100.0, "change": 0.35, "status": "up"}
    }
    summary = fetch_live_market_summary()
    live_data = {
        "Bitcoin (BTC)": {"price": summary.get("Bitcoin", {}).get("price", 6250000.0), "change": summary.get("Bitcoin", {}).get("change_pct", 1.45), "status": "up"},
        "NIFTY 50": {"price": summary.get("NIFTY_50", {}).get("price", 25200.0), "change": summary.get("NIFTY_50", {}).get("change_pct", 0.40), "status": "up"},
        "Gold (per 10g)": {"price": summary.get("Gold", {}).get("price", 78500.0), "change": summary.get("Gold", {}).get("change_pct", -0.25), "status": "down"},
        "BSE SENSEX": {"price": summary.get("BSE_Sensex", {}).get("price", 82100.0), "change": summary.get("BSE_Sensex", {}).get("change_pct", 0.35), "status": "up"}
    }
    return jsonify({"status": "success", "market": live_data, "server_time": time.time()})

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
        return jsonify({"status": "error", "message": "Username and phone are required."}), 400

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
    if 'user' not in session: 
        return jsonify({"status": "error", "message": "User session expired."}), 401
    
    if session.get('is_admin', False):
        return jsonify({"status": "error", "message": "Administrators cannot generate plans."}), 403

    data = request.json or {}
    mode = data.get('mode', 'goal')
    years = max(int(data.get('years', 3)), 1)
    statement = data.get('statement', '').strip()
    input_val = float(data.get('input_val', 0) or 0)
    budget_level = data.get('travel_style', 'mid')
    risk_tier = data.get('risk_tier', 'mid')

    rate_map = {"low": 0.085, "mid": 0.125, "high": 0.160}
    expected_rate = rate_map.get(risk_tier, 0.125)

    default_allocations = {
        "low": {"Stock_Market_Index": 20.0, "Mutual_Funds": 40.0, "Real_Estate_REITs": 20.0, "Gold_Precious_Metals": 20.0, "Cryptocurrency_BTC": 0.0},
        "mid": {"Stock_Market_Index": 40.0, "Mutual_Funds": 25.0, "Real_Estate_REITs": 15.0, "Gold_Precious_Metals": 15.0, "Cryptocurrency_BTC": 5.0},
        "high": {"Stock_Market_Index": 45.0, "Mutual_Funds": 15.0, "Real_Estate_REITs": 10.0, "Gold_Precious_Metals": 10.0, "Cryptocurrency_BTC": 20.0}
    }

    r = expected_rate / 12
    n = years * 12

    if mode == 'budget':
        monthly_sip = max(input_val, 500.0)
        sip_growth_factor = (((1 + r)**n - 1) / r) * (1 + r)
        target_corpus = round(monthly_sip * sip_growth_factor, 2)
        total_invested = round(monthly_sip * n, 2)
        goal_title = f"Monthly SIP Plan (₹{monthly_sip:,.0f}/mo)"
        risk_profile = f"{risk_tier.capitalize()} Risk Strategy"
        allocation = default_allocations.get(risk_tier)
        ai_rationale = (f"Fixed monthly investment of ₹{monthly_sip:,.0f} compounding over {years} years. "
                        f"At a projected CAGR of {expected_rate*100:.1f}%, accumulated value is ₹{target_corpus:,.0f}.")

    elif mode == 'corpus':
        target_corpus = max(input_val, 1000.0)
        monthly_sip = round(target_corpus / ( (((1 + r)**n - 1) / r) * (1 + r) ), 2)
        total_invested = round(monthly_sip * n, 2)
        goal_title = f"Target Corpus of ₹{target_corpus:,.0f}"
        risk_profile = f"{risk_tier.capitalize()} Risk Strategy"
        allocation = default_allocations.get(risk_tier)
        ai_rationale = (f"Target corpus of ₹{target_corpus:,.0f} in {years} years. "
                        f"At {expected_rate*100:.1f}% annual CAGR, monthly SIP required is ₹{monthly_sip:,.0f}.")

    else:
        # High-speed AI execution
        ai_result = call_ai_financial_planner_fast(
            statement, years, mode, input_val, budget_level, risk_tier
        )

        if ai_result and isinstance(ai_result, dict) and "target_corpus" in ai_result:
            goal_title = ai_result.get("destination_title", statement or "Custom Goal")
            target_corpus = float(ai_result.get("target_corpus", 350000))
            ai_rationale = ai_result.get("ai_rationale", "")
            risk_profile = f"{risk_tier.capitalize()} Risk Strategy"
            allocation = ai_result.get("allocation_pcts", default_allocations.get(risk_tier))
            expected_rate = float(ai_result.get("expected_annual_rate", expected_rate))
            r = expected_rate / 12
        else:
            tier_cost = {"budget": 150000, "mid": 450000, "luxury": 1200000}.get(budget_level, 450000)
            target_corpus = round(tier_cost * ((1.05) ** years), 2)
            goal_title = statement if statement else "Custom Financial Goal"
            risk_profile = f"{risk_tier.capitalize()} Risk Strategy"
            allocation = default_allocations.get(risk_tier)
            ai_rationale = f"Applied dynamic baseline of ₹{tier_cost:,} adjusted for {years} years at 5% annual inflation."

        monthly_sip = round(target_corpus / ( (((1 + r)**n - 1) / r) * (1 + r) ), 2)
        total_invested = round(monthly_sip * n, 2)

    tot_pct = sum(allocation.values())
    if tot_pct > 0:
        allocation = {k: round((v / tot_pct) * 100, 1) for k, v in allocation.items()}

    budget_label_map = {"budget": "Low Budget", "mid": "Mid Budget", "luxury": "High Budget"}
    readable_budget = budget_label_map.get(budget_level, "Mid Budget")

    portfolio_detailed = {}
    for asset, pct in allocation.items():
        pct_val = float(pct)
        allocated_principal = round(total_invested * (pct_val / 100.0), 2)
        projected_return = round(allocated_principal * ((1 + expected_rate) ** years), 2)
        portfolio_detailed[asset] = {
            "pct": pct_val,
            "amount": allocated_principal,
            "projected_return": projected_return
        }

    return jsonify({
        "status": "success",
        "data": {
            "goal_identified": goal_title,
            "travel_style": readable_budget,
            "risk_profile": risk_profile,
            "tenure_years": years,
            "duration_days": 0,
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
    
    if session.get('is_admin', False):
        return jsonify({"status": "error", "message": "Admins cannot execute investments."}), 403

    data = request.json or {}; plan = data.get('plan', {}); u = session['user']

    ledger = load_ledger()
    record_id = len(ledger) + 1
    tx = {
        "record_id": record_id,
        "user": u,
        "goal": plan.get('goal_identified'),
        "travel_style": plan.get('travel_style', 'Mid Budget'),
        "duration_days": 0,
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
