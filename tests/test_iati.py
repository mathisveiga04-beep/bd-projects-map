import os
import sys

_APP = os.path.join(os.path.dirname(__file__), "..", "bd_platform_cloud_gemini_v1 2", "backend", "app")
sys.path.insert(0, os.path.abspath(_APP))

from scrapers.iati import _parse_activities, _funder, _is_relevant, _activity_url, _ADB_REF  # noqa: E402
from official_status import official_status_to_fr  # noqa: E402

_ROWS = [
    {"reporting_ref": "XM-DAC-44000", "reporting_org": "World Bank",
     "status_code": "2", "title": "National Road Rehabilitation Project",
     "description": "Rehabilitation of civil works", "aid": "WB-001"},
    {"reporting_ref": "XM-DAC-903", "reporting_org": "GCF",
     "status_code": "1", "title": "Urban Water Supply Infrastructure",
     "description": "New water supply network", "aid": "GCF-002"},
    {"reporting_ref": _ADB_REF, "reporting_org": "ADB",
     "status_code": "2", "title": "ADB Highway Construction", "aid": "ADB-003"},
    {"reporting_ref": "XM-DAC-41114", "reporting_org": "UNDP",
     "status_code": "2", "title": "Governance capacity workshop",
     "description": "Training and policy dialogue", "aid": "UNDP-004"},
    {"reporting_ref": "XM-DAC-44000", "reporting_org": "World Bank",
     "status_code": "4", "title": "Old Bridge Construction", "aid": "WB-005"},
]


def test_exclut_adb_statuts_non_courants_et_hors_sujet():
    out = _parse_activities(_ROWS, "Cambodia")
    titles = [o.title for o in out]
    assert "ADB Highway Construction" not in titles  # ADB couvert ailleurs
    assert "Old Bridge Construction" not in titles   # status 4 (clos)
    assert "Governance capacity workshop" not in titles  # pas un projet physique
    assert "National Road Rehabilitation Project" in titles
    assert "Urban Water Supply Infrastructure" in titles
    assert len(out) == 2


def test_opportunity_bien_formee():
    out = _parse_activities(_ROWS, "Cambodia")
    o = next(x for x in out if x.title.startswith("National Road"))
    assert o.funder == "Banque mondiale"
    assert o.source == "IATI (Banque mondiale)"
    assert o.country == "Cambodia"
    assert o.official_status == "2"
    assert "WB-001" in o.source_url


def test_funder_fallback():
    assert _funder("XM-DAC-46004", "ADB") == "ADB"
    assert _funder("XX-UNKNOWN", "Some Org") == "Some Org"
    assert _funder("XX-UNKNOWN", "") == "XX-UNKNOWN"
    assert _funder("", "") == "IATI"


def test_relevance():
    assert _is_relevant("Hospital construction project")
    assert _is_relevant("rural road rehabilitation")
    assert not _is_relevant("policy dialogue and training")


def test_accord_avec_official_status():
    assert official_status_to_fr("2") == "En cours"
    assert official_status_to_fr("1") == "En attente"


def test_entrees_robustes():
    assert _parse_activities([], "Cambodia") == []
    assert _parse_activities(None, "Cambodia") == []
    assert _parse_activities(["x", 5, None], "Cambodia") == []


def test_activity_url():
    assert "aid=WB-001" in _activity_url("WB-001")
    assert _activity_url("").startswith("https://d-portal.org")
