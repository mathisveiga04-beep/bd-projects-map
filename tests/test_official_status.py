"""Tests de non-régression du mapping des statuts OFFICIELS de source
vers les valeurs FR canoniques (official_status.py).

Verrouille la régle : le statut affiché sur la carte est FIDELE au statut
officiel de la source quand il existe ; sinon repli sur l'IA (retour vide).
"""
import os
import sys

_APP = os.path.join(
    os.path.dirname(__file__), "..",
    "bd_platform_cloud_gemini_v1 2", "backend", "app",
)
sys.path.insert(0, os.path.abspath(_APP))

from official_status import official_status_to_fr  # noqa: E402


def test_world_bank_valeurs_reelles():
    # Valeurs reelles du champ projectstatusdisplay de la Banque mondiale.
    assert official_status_to_fr("Pipeline") == "En attente"
    assert official_status_to_fr("Active") == "En cours"
    assert official_status_to_fr("Closed") == "Terminé"
    assert official_status_to_fr("Dropped") == "Annulé"


def test_synonymes():
    assert official_status_to_fr("Concept") == "En attente"
    assert official_status_to_fr("Implementation") == "En cours"
    assert official_status_to_fr("Completed") == "Terminé"
    assert official_status_to_fr("Cancelled") == "Annulé"


def test_insensible_casse_et_accents():
    assert official_status_to_fr("  ACTIVE  ") == "En cours"
    assert official_status_to_fr("Terminé") == "Terminé"


def test_absent_ou_inconnu_retombe_sur_ia():
    # Vide / None / inconnu -> retour vide => l'appelant garde l'analyse Gemini.
    assert official_status_to_fr("") == ""
    assert official_status_to_fr(None) == ""
    assert official_status_to_fr("Bogus XYZ") == ""
