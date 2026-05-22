import json
import os
from typing import Dict, Any
from dotenv import load_dotenv

load_dotenv()

SYSTEM_PROMPT = """You are a business development analyst for Artelia Cambodia.
Analyze construction, infrastructure, water, environment, urban planning and building opportunities.
Return ONLY valid JSON with these keys:
summary, sector, project_type, city, country, funder, estimated_budget, deadline,
confidence, opportunity_size, priority, recommendation, scope_summary.
Use concise English. If unknown, use an empty string or 'unknown'."""


def _fallback(title: str, text: str) -> Dict[str, Any]:
    joined = f"{title}\n{text}".lower()
    sector = ""
    if any(k in joined for k in ["water", "wastewater", "drainage", "flood"]):
        sector = "Water / Drainage"
    elif any(k in joined for k in ["building", "hospital", "hotel", "office"]):
        sector = "Building"
    elif any(k in joined for k in ["road", "bridge", "transport"]):
        sector = "Infrastructure"
    priority = "high" if any(k in joined for k in ["eoi", "reoi", "rfp", "deadline", "expression of interest"]) else "medium"
    return {
        "summary": (text[:500] + "...") if len(text) > 500 else text,
        "sector": sector or "To qualify",
        "project_type": "Tender / Opportunity" if priority == "high" else "Project lead",
        "city": "",
        "country": "Cambodia",
        "funder": "",
        "estimated_budget": "unknown",
        "deadline": "",
        "confidence": "medium",
        "opportunity_size": "unknown",
        "priority": priority,
        "recommendation": "watch",
        "scope_summary": "Review source and qualify Artelia scope."
    }


def analyze_with_gemini(title: str, text: str, source_url: str = "") -> Dict[str, Any]:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip()
    if not api_key:
        return _fallback(title, text)

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        prompt = f"{SYSTEM_PROMPT}\n\nTitle: {title}\nSource URL: {source_url}\nText:\n{text[:12000]}"
        response = client.models.generate_content(model=model_name, contents=prompt)
        raw = (response.text or "").strip()
        raw = raw.removeprefix("```json").removesuffix("```").strip()
        return json.loads(raw)
    except Exception as exc:
        data = _fallback(title, text)
        data["ai_summary"] = f"Gemini fallback used: {exc}"
        return data
