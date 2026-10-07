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
    return summary

def call_ai_financial_planner(intent_text, tenure_years, mode, budget_or_corpus, budget_level, risk_tier, market_snapshot):
    if not GENAI_AVAILABLE:
        print("[OmniVest Error] google-genai library is not installed.")
        return None
    if not GEMINI_API_KEY:
        print("[OmniVest Error] GEMINI_API_KEY environment variable is missing or empty.")
        return None

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        prompt = f"""
You are an expert quantitative financial research advisor and autonomous pricing intelligence engine.
All calculated monetary figures must be in Indian Rupees (INR / ₹).

Current Live Market Data (yFinance):
{json.dumps(market_snapshot, indent=2)}

User Request & Parameters:
- Custom Goal / Desire: "{intent_text}"
- Planning Mode: {mode}
- User Numeric Input: {budget_or_corpus}
- Tenure: {tenure_years} years
- Budget Scale: {budget_level} (Low Budget, Mid Budget, High Budget)
- Risk Preference: {risk_tier} (Low Risk, Mid Risk, High Risk)

YOUR RESEARCH & ESTIMATION TASK:
1. Deeply understand the user's specific goal. Conduct mental domain research:
   - IF AN EV OR VEHICLE (e.g. "I want to buy an EV"):
     * Determine which exact EV model fits the requested budget level in India (e.g. Tata Tiago EV / MG Comet for Low; Tata Nexon EV / Mahindra XUV400 / MG ZS EV for Mid; BYD Seal / Hyundai Ioniq 5 / BMW i4 for High).
     * Identify real on-road pricing in India (base price + RTO + battery insurance).
   - IF A TRIP (e.g. "trip to Italy", "Netherlands for 100 days"):
     * Detect duration in days (e.g. 100 days). If not stated, assume 10 days.
     * Research realistic round-trip flights from Indian metros.
     * Calculate per-day expenses (stay, food, transit, entry passes) converted to INR at live exchange rates.
     * Total present trip cost = Flights + (Daily Expense * Days).
   - IF OTHER MILESTONES (e.g. "start a café", "MBA in UK", "wedding", "buy a flat down payment"):
     * Break down the realistic present cost in India or abroad based on the chosen tier ({budget_level}).
2. Factor in realistic inflation:
   * Apply compound inflation of 5% to 6% per annum over {tenure_years} years: Target Corpus = Present Cost * ((1 + 0.05) ** {tenure_years}).
3. Determine Multi-Asset Portfolio Allocation for '{risk_tier}' risk:
   * Stock_Market_Index, Mutual_Funds, Real_Estate_REITs, Gold_Precious_Metals, Cryptocurrency_BTC.
   * Total percentages MUST sum up to exactly 100.
4. Estimate realistic overall portfolio CAGR (e.g. 0.08 to 0.17).

OUTPUT FORMAT:
Respond ONLY with a valid, clean JSON object (no markdown, no ``` backticks):
{{
  "destination_title": "Precise goal title (e.g. 'Tata Nexon EV Empowered Long Range' or '100-Day Netherlands Trip')",
  "target_corpus": <final integer in INR after inflation>,
  "present_cost_inr": <estimated present cost in INR>,
  "expected_annual_rate": <decimal, e.g. 0.12>,
  "risk_profile_description": "{risk_tier.capitalize()} Risk Portfolio",
  "ai_rationale": "Detail the exact model/flight/daily costs researched, exchange rates used, inflation compounding over {tenure_years} years, and why this asset allocation was chosen.",
  "allocation_pcts": {{
     "Stock_Market_Index": <number>,
     "Mutual_Funds": <number>,
     "Real_Estate_REITs": <number>,
     "Gold_Precious_Metals": <number>,
     "Cryptocurrency_BTC": <number>
  }}
}}
"""
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2
            )
        )
        
        raw_text = response.text.strip()
        cleaned_text = re.sub(r'^```json\s*', '', raw_text)
        cleaned_text = re.sub(r'\s*```$', '', cleaned_text)
        
        parsed = json.loads(cleaned_text)
        print(f"[OmniVest AI Success] Calculated target corpus: ₹{parsed.get('target_corpus'):,}")
        return parsed

    except Exception as e:
        print(f"[OmniVest AI Exception] Call failed: {e}")
        return None

# ==========================================
# API ENDPOINTS
# ==========================================
@app.route('/api/market-prices', methods=['GET'])
def get_market_prices():
    tickers = {
        "Bitcoin (BTC)": "BTC-INR",
        "NIFTY 50": "^NSEI",
        "Gold (per 10g)": "GC=F",
        "BSE SENSEX": "^BSESN"
    }
    fallbacks = {
        "Bitcoin (BTC)": {"price": 6250000.0, "change": 1.45, "status": "up"},
        "NIFTY 50": {"price": 25200.0, "change": 0.40, "status": "up"},
        "Gold (per 10g)": {"price": 78500.0, "change": -0.25, "status": "down"},
        "BSE SENSEX": {"price": 82100.0, "change": 0.35, "status": "up"}
    }
    live_data = {}
    for name, symbol in tickers.items():
        try:
            t = yf.Ticker(symbol)
            df = t.history(period="2d")
            if len(df) >= 1:
                cur = float(df['Close'].iloc[-1])
                prev = float(df['Close'].iloc[-2]) if len(df) >= 2 else cur
                chg = round(((cur - prev) / prev) * 100, 2)
                live_data[name] = {"price": round(cur, 2), "change": chg, "status": "up" if chg >= 0 else "down"}
            else:
                live_data[name] = fallbacks[name]
        except Exception:
            live_data[name] = fallbacks[name]
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
    if 'user' not in session: return jsonify({"status": "error"}), 401
    
    if session.get('is_admin', False):
        return jsonify({"status": "error", "message": "Administrators only oversee portfolios and cannot create investment plans."}), 403

    data = request.json or {}
    mode = data.get('mode', 'goal')
    years = max(int(data.get('years', 3)), 1)
    statement = data.get('statement', '').strip()
    input_val = float(data.get('input_val', 0) or 0)
    budget_level = data.get('travel_style', 'mid')
    risk_tier = data.get('risk_tier', 'mid')

    market_snapshot = fetch_live_market_summary()

    # Rate calibrations
    rate_map = {"low": 0.085, "mid": 0.125, "high": 0.160}
    expected_rate = rate_map.get(risk_tier, 0.125)

    default_allocations = {
        "low": {"Stock_Market_Index": 20.0, "Mutual_Funds": 40.0, "Real_Estate_REITs": 20.0, "Gold_Precious_Metals": 20.0, "Cryptocurrency_BTC": 0.0},
        "mid": {"Stock_Market_Index": 40.0, "Mutual_Funds": 25.0, "Real_Estate_REITs": 15.0, "Gold_Precious_Metals": 15.0, "Cryptocurrency_BTC": 5.0},
        "high": {"Stock_Market_Index": 45.0, "Mutual_Funds": 15.0, "Real_Estate_REITs": 10.0, "Gold_Precious_Metals": 10.0, "Cryptocurrency_BTC": 20.0}
    }

    r = expected_rate / 12
    n = years * 12

    # MODE HANDLING WITH FIXED SIP & LOWER MINIMUMS
    if mode == 'budget':
        # FIX 1: User explicitly gives monthly SIP amount. SIP MUST remain strictly constant.
        monthly_sip = max(input_val, 500.0)
        # Accurate geometric compound annuity formula
        sip_growth_factor = (((1 + r)**n - 1) / r) * (1 + r)
        target_corpus = round(monthly_sip * sip_growth_factor, 2)
        total_invested = round(monthly_sip * n, 2)
        goal_title = f"Monthly SIP Accumulator (₹{monthly_sip:,.0f}/mo)"
        risk_profile = f"{risk_tier.capitalize()} Risk Strategy"
        allocation = default_allocations.get(risk_tier)
        ai_rationale = (f"Fixed SIP of ₹{monthly_sip:,.0f}/month invested over {years} years ({n} months). "
                        f"At a {risk_tier.capitalize()} risk projected CAGR of {expected_rate*100:.1f}%, your wealth compounds "
                        f"to ₹{target_corpus:,.0f} (Gain: ₹{target_corpus - total_invested:,.0f}).")

    elif mode == 'corpus':
        # FIX 2: Fixed target amount allows any goal (e.g. ₹50,000, ₹25,000, etc.)
        target_corpus = max(input_val, 1000.0)
        monthly_sip = round(target_corpus / ( (((1 + r)**n - 1) / r) * (1 + r) ), 2)
        total_invested = round(monthly_sip * n, 2)
        goal_title = f"Target Corpus of ₹{target_corpus:,.0f}"
        risk_profile = f"{risk_tier.capitalize()} Risk Strategy"
        allocation = default_allocations.get(risk_tier)
        ai_rationale = (f"Target payout of ₹{target_corpus:,.0f} in {years} years. "
                        f"At {expected_rate*100:.1f}% annual CAGR, investing ₹{monthly_sip:,.0f}/month accumulates your goal.")

    else:
        # mode == 'goal': Let Gemini autonomously research pricing and model
        ai_result = call_ai_financial_planner(
            statement, years, mode, input_val, budget_level, risk_tier, market_snapshot
        )

        if ai_result:
            goal_title = ai_result.get("destination_title", statement or "Custom Financial Goal")
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
            ai_rationale = f"[Offline Fallback] Estimated baseline of ₹{tier_cost:,} compounded over {years} years at 5% annual inflation."

        monthly_sip = round(target_corpus / ( (((1 + r)**n - 1) / r) * (1 + r) ), 2)
        total_invested = round(monthly_sip * n, 2)

    # Normalize allocation to exactly 100%
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
        return jsonify({"status": "error", "message": "Admins are strictly supervisors and cannot commit investments."}), 403

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
