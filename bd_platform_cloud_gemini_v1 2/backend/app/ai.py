import json
import os
import time
from typing import Dict, Any
from dotenv import load_dotenv
from .sources import source_keyword_context

load_dotenv()

SYSTEM_PROMPT = """You are a CRITICAL business development analyst for MVE in Cambodia and the ASEAN region.
Analyze project management, architecture, energy, construction, infrastructure, water,
environment, urban planning and building opportunities.
Be selective: only surface opportunities where MVE can realistically still win and add value.
Return ONLY valid JSON with these keys:
summary, sector, project_type, city, country, funder, estimated_budget, deadline,
confidence, opportunity_size, priority, recommendation, scope_summary, score, message_fr, project_status.
project_status: lifecycle status, EXACTLY one of these five French values: "Démarré" (work started / construction underway), "En attente" (planned or pending, not yet started), "En cours" (actively ongoing / in progress), "Terminé" (completed / delivered), "Annulé" (cancelled / abandoned). Infer it from the source text; if unclear use "En attente".
score: integer 1-10 measuring relevance for MVE (10 = perfect match).
recommendation: one of "pursue", "watch", "discard".
CRITICAL FILTERING RULES (be strict):
- TENDERS / APPELS D'OFFRE (project_type mentioning tender, EOI, REOI, RFP, expression of interest):
  ONLY treat as a real opportunity if the work is NOT yet launched. If the project is already
  launched, ongoing, under construction, awarded, started, or has been running since 2022 or earlier,
  it is NOT a tender opportunity for MVE: set score to 1, priority to "low",
  recommendation to "discard", and state in scope_summary that it is already launched/ongoing.
- RENOVATION: ONLY include EXISTING buildings/assets where a renovation, refurbishment, retrofit,
  "reprise" or advisory on existing installations is actually possible. If it is a greenfield /
  brand-new build with no existing asset to renovate, do NOT classify or propose it as renovation:
  set score to 2 or less, priority to "low", recommendation to "discard", and explain why in
  scope_summary. Always make the launch status and whether an existing building is involved explicit
  inside summary and scope_summary.
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
        "country": "",  # infere par l'IA / le scraper (multi-pays ASEAN)
        "funder": "",
        "estimated_budget": "unknown",
        "deadline": "",
        "confidence": "medium",
        "opportunity_size": "unknown",
        "priority": priority,
        "recommendation": "watch",
        "scope_summary": "Review source and qualify MVE scope.",
        "score": score,
        "message_fr": message_fr,
        "project_status": "En attente",
    }

def _enforce_criticality(data: Dict[str, Any]) -> Dict[str, Any]:
    """Safety net: drop already-launched tenders and non-existing-building renovations.

    Works only on the existing JSON keys, so it never changes the data schema.
    """
    rec = str(data.get("recommendation", "")).lower()
    blob = " ".join(
        str(data.get(k, "")) for k in ("project_type", "scope_summary", "summary", "priority")
    ).lower()

    is_tender = any(
        k in blob
        for k in ["tender", "appel d'offre", "appel d offre", "eoi", "reoi", "rfp", "expression of interest"]
    )
    launched = any(
        k in blob
        for k in [
            "already launched",
            "under construction",
            "works ongoing",
            "ongoing construction",
            "construction started",
            "contract awarded",
            "already awarded",
            "in progress",
            "launched in 2022",
            "launched since 2022",
            "started in 2022",
            "ongoing since",
        ]
    )
    is_renovation = any(
        k in blob for k in ["renovation", "refurbish", "retrofit", "reprise", "rehabilitation"]
    )
    no_existing = any(
        k in blob for k in ["greenfield", "new build", "new-build", "no existing building", "brand new"]
    )

    drop = rec in ("discard", "skip", "ignore", "reject")
    if is_tender and launched:
        drop = True
    if is_renovation and no_existing:
        drop = True

    if drop:
        try:
            data["score"] = min(int(data.get("score", 5) or 5), 2)
        except (ValueError, TypeError):
            data["score"] = 2
        data["priority"] = "low"
        data["recommendation"] = "discard"
    return data

def _normalize_project_status(value: Any) -> str:
    """Coerce any value to one of the 5 canonical French lifecycle statuses."""
    import unicodedata
    raw = ("" if value is None else str(value)).strip().lower()
    raw = "".join(c for c in unicodedata.normalize("NFD", raw) if unicodedata.category(c) != "Mn")
    if not raw:
        return "En attente"
    if any(k in raw for k in ("annul", "cancel", "abandon", "withdraw")):
        return "Annulé"
    if any(k in raw for k in ("termin", "complet", "deliver", "finish", "closed", "awarded", "done", "achev")):
        return "Terminé"
    if any(k in raw for k in ("en cours", "ongoing", "in progress", "underway", "running", "execution", "active")):
        return "En cours"
    if any(k in raw for k in ("demarr", "start", "launch", "construction", "kickoff", "kick-off", "commenc", "began", "begun")):
        return "Démarré"
    return "En attente"


def analyze_with_gemini(title: str, text: str, source_url: str = "") -> Dict[str, Any]:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
    if not api_key:
        return _fallback(title, text)

    last_error: Exception | None = None
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        prompt = f"{SYSTEM_PROMPT}\n\nTitle: {title}\nSource URL: {source_url}\nText:\n{text[:12000]}"
        _models = []
        for _m in (model_name, "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-flash-latest"):
            _m = (_m or "").strip()
            if _m and _m not in _models:
                _models.append(_m)
        response = None
        for _mdl in _models:
            _ok = False
            for attempt in range(2):
                try:
                    response = client.models.generate_content(model=_mdl, contents=prompt)
                    _ok = True
                    break
                except Exception as exc:
                    last_error = exc
                    time.sleep(0.6 * (attempt + 1))
            if _ok:
                break
        if response is None:
            raise last_error or RuntimeError("Gemini: aucun modele disponible")
        raw = (response.text or "").strip()
        raw = raw.removeprefix("```json").removesuffix("```").strip()
        data = json.loads(raw)
        # ensure score is int
        if "score" in data:
            try:
                data["score"] = int(data["score"])
            except (ValueError, TypeError):
                data["score"] = 5
        data["project_status"] = _normalize_project_status(data.get("project_status"))
        data = _enforce_criticality(data)
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
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
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
