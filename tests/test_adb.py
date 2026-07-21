"""Tests du connecteur ADB (IATI / d-portal).

Le parsing est PUR (aucun reseau) : on verifie le filtrage par statut IATI,
la construction des Opportunity, et l'accord avec official_status.py.
"""
import os
import sys

_APP = os.path.join(
    os.path.dirname(__file__), "..",
    "bd_platform_cloud_gemini_v1 2", "backend", "app",
)
sys.path.insert(0, os.path.abspath(_APP))

from scrapers.adb import _parse_activities, _activity_url  # noqa: E402
from official_status import official_status_to_fr  # noqa: E402


_ROWS = [
    {"aid": "XM-DAC-46004-1", "title": "Phnom Penh Water", "status_code": "2",
     "country_code": "KH", "day_start": "2024-01-01", "day_end": "2027-01-01"},
    {"aid": "XM-DAC-46004-2", "title": "Old Closed Road", "status_code": "4",
     "country_code": "KH"},
    {"aid": "XM-DAC-46004-3", "title": "Future Pipeline", "status_code": "1",
     "country_code": "KH"},
    {"aid": "XM-DAC-46004-4", "title": "Cancelled Thing", "status_code": "5"},
]


def test_ne_garde_que_les_statuts_courants():
    items = _parse_activities(_ROWS, "Cambodia")
    titles = [i.title for i in items]
    # Statuts 1 (Pipeline) et 2 (Implementation) uniquement.
    assert "Phnom Penh Water" in titles
    assert "Future Pipeline" in titles
    # Statuts 4 (Closed) et 5 (Cancelled) ecartes a la source.
    assert "Old Closed Road" not in titles
    assert "Cancelled Thing" not in titles
    assert len(items) == 2


def test_opportunity_bien_formee():
    items = _parse_activities(_ROWS, "Cambodia")
    opp = items[0]
    assert opp.funder == "ADB"
    assert opp.source == "ADB (IATI)"
    assert opp.country == "Cambodia"
    assert opp.official_status == "2"
    assert "XM-DAC-46004-1" in opp.source_url


def test_accord_avec_official_status():
    # Le code IATI transmis doit se traduire correctement en FR.
    items = _parse_activities(_ROWS, "Cambodia")
    fr = {i.title: official_status_to_fr(i.official_status) for i in items}
    assert fr["Phnom Penh Water"] == "En cours"    # 2 -> Implementation
    assert fr["Future Pipeline"] == "En attente"   # 1 -> Pipeline


def test_entrees_robustes():
    # Entrees vides / non-dict / statut manquant ne cassent rien.
    assert _parse_activities([], "Cambodia") == []
    assert _parse_activities([None, "x", {}], "Cambodia") == []
    assert _parse_activities(None, "Cambodia") == []


def test_activity_url():
    assert "aid=XM-DAC-46004-9" in _activity_url("XM-DAC-46004-9")
    assert _activity_url("").startswith("https://d-portal.org/ctrack.html")
