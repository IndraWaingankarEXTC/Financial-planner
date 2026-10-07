import json
import os
from flask import Flask, jsonify, render_template, request
from google import genai
from google.genai import types

app = Flask(__name__)

# Reads GEMINI_API_KEY or GOOGLE_API_KEY from Render Environment Variables
API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

client = None
if API_KEY:
    client = genai.Client(api_key=API_KEY)


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/api/calculate-plan", methods=["POST"])
def calculate_plan():
    if not client:
        return (
            jsonify(
                {
                    "success": False,
                    "error": "GEMINI_API_KEY is not configured in Render environment variables.",
                }
            ),
            500,
        )

    data = request.get_json(silent=True) or {}
    description = data.get("description", "").strip()

    if not description:
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Please describe your financial or investment goal.",
                }
            ),
            400,
        )

    # Prompt forcing Gemini to compute exact math rather than guessing
    prompt = f"""
    You are OmniVest's Lead Financial Planner and Quantitative Strategist.
    A salaried user provided the following financial goal/scenario:
    \"\"\"{description}\"\"\"

    Strict Instructions:
    1. Understand their target, timeline, cashflows, and risk profile.
    2. Perform exact mathematical calculations:
       - Compounding or savings targets per month/week/day.
       - Realistic runway, asset allocation percentage, or inflation/returns projections.
       - Do not guess or insert arbitrary random numbers. Derive numbers strictly from their stated parameters or sound financial models (e.g. 7-12% equity index CAGR, 6% debt, emergency buffer).
    3. Determine concrete execution milestones.

    Return ONLY a valid JSON object matching this schema:
    {{
        "title": "Clear Financial Strategy Title",
        "category": "e.g., Wealth Accumulation / Emergency Buffer / Debt Elimination / Retirement",
        "feasibility": "High / Moderate / Aggressive (with numerical justification)",
        "calculated_metrics": [
            {{"label": "Metric Name", "value": "Calculated value (with currency)", "details": "How it was calculated"}}
        ],
        "milestones": [
            {{"period": "e.g., Month 1-3", "task": "Actionable task", "deliverable": "Target portfolio/savings balance"}}
        ],
        "strategic_recommendation": "Decisive, professional advice aligned with OmniVest's promise: simpler, smarter, and accessible."
    }}
    """

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,  # Low temperature guarantees deterministic mathematical reasoning
            ),
        )

        plan_data = json.loads(response.text)
        return jsonify({"success": True, "plan": plan_data})

    except Exception as e:
        return (
            jsonify({"success": False, "error": f"Calculation failed: {str(e)}"}),
            500,
        )


@app.route("/healthz")
def healthz():
    return {"status": "ok"}, 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
           
