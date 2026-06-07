import json
import os
import time
from typing import Dict, Any
from dotenv import load_dotenv
from .sources import source_keyword_context

load_dotenv()

SYSTEM_PROMPT = """You are a business development analyst for MVE in Cambodia.
Analyze project management, architecture, energy, construction, infrastructure, water,
environment, urban planning and building opportunities.
Return ONLY valid JSON with these keys:
summary, sector, project_type, city, country, funder, estimated_budget, deadline,
confidence, opportunity_size, priority, recommendation, scope_summary, score, message_fr.

score: integer 1-10 measuring relevance for MVE (10 = perfect match).
message_fr: a 3-sentence professional French email proposing MVE's services
  for this specific opportunity. Mention project management, architecture, energy,
  sustainability, technical engineering or infrastructure expertise when relevant.
Use concise English for all fields except message_fr. If unknown, use empty string or 'unknown'.

Default Cambodia opportunity sources and keywords to prioritize:
{source_keywords}
""".format(source_keywords=source_keyword_context())


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
    score = 7 if priority == "high" else 5
    message_fr = (
        f"Madame, Monsieur, MVE souhaite vous proposer ses services de project management, "
        f"d'architecture, d'\u00e9nergie et de conseil technique pour l'opportunit\u00e9 '{title}'. "
        f"Notre approche associe coordination projet, performance technique et durabilit\u00e9 afin "
        f"de contribuer concr\u00e8tement au succ\u00e8s de ce projet. Nous restons \u00e0 votre disposition "
        f"pour un premier \u00e9change."
    )
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
        "scope_summary": "Review source and qualify Artelia scope.",
        "score": score,
        "message_fr": message_fr,
    }


def analyze_with_gemini(title: str, text: str, source_url: str = "") -> Dict[str, Any]:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip()
    if not api_key:
        return _fallback(title, text)

    last_error: Exception | None = None
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        prompt = f"{SYSTEM_PROMPT}\n\nTitle: {title}\nSource URL: {source_url}\nText:\n{text[:12000]}"
        for attempt in range(3):
            try:
                response = client.models.generate_content(model=model_name, contents=prompt)
                break
            except Exception as exc:
                last_error = exc
                if attempt == 2:
                    raise
                time.sleep(0.8 * (attempt + 1))
        raw = (response.text or "").strip()
        raw = raw.removeprefix("```json").removesuffix("```").strip()
        data = json.loads(raw)
        # ensure score is int
        if "score" in data:
            try:
                data["score"] = int(data["score"])
            except (ValueError, TypeError):
                data["score"] = 5
        return data
    except Exception as exc:
        data = _fallback(title, text)
        data["ai_error"] = f"Gemini fallback: {last_error or exc}"
        return data


def _fallback_generate(prompt: str, mode: str = "general") -> str:
    compact = " ".join(prompt.split())
    if mode == "linkedin":
        return (
            "Bonjour, je me permets de vous contacter au nom de MVE au sujet de cette opportunite. "
            "Nos equipes peuvent accompagner les sujets de project management, architecture, energie, "
            "infrastructure et performance technique. Seriez-vous disponible pour un court echange afin "
            "d'identifier les besoins et les prochaines etapes possibles ?"
        )
    if mode == "brief":
        return (
            "Brief BD: prioriser les opportunites a forte valeur technique, verifier les sources bailleurs, "
            "contacter les prospects non qualifies et suivre les projets project management, architecture, "
            "energie, eau, infrastructure et resilience climatique. "
            f"Contexte analyse localement: {compact[:500]}"
        )
    return f"Synthese IA locale: {compact[:800]}"


def generate_with_gemini(prompt: str, max_tokens: int = 700, mode: str = "general") -> Dict[str, Any]:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip()
    if not api_key:
        return {"text": _fallback_generate(prompt, mode), "provider": "local-fallback"}

    last_error: Exception | None = None
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        bounded_prompt = (
            "You are Gemini working for MVE business development in Cambodia. "
            "Be concise, practical and directly usable.\n\n"
            f"Mode: {mode}\n"
            f"Default Cambodia source keywords:\n{source_keyword_context()}\n\n"
            f"Task:\n{prompt[:12000]}"
        )
        for attempt in range(3):
            try:
                response = client.models.generate_content(model=model_name, contents=bounded_prompt)
                break
            except Exception as exc:
                last_error = exc
                if attempt == 2:
                    raise
                time.sleep(0.8 * (attempt + 1))
        return {"text": (response.text or "").strip(), "provider": "gemini", "model": model_name}
    except Exception as exc:
        return {
            "text": _fallback_generate(prompt, mode),
            "provider": "local-fallback",
            "ai_error": f"Gemini fallback: {last_error or exc}",
        }
