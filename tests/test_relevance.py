"""Tests d'integration de la porte anti-fuite relevance() (common.py).

Verrouille l'invariant metier central : un projet dont le stage indique
execution / attribue / cloture / annule DOIT etre filtre ("filtered"), et
seuls les projets en amont (pipeline / preparation / appel) sont conserves
("kept"). Verifie aussi le chainage stage_map -> relevance : aucun statut
source terminal ne doit fuir, et le defaut conservateur "closed" filtre bien.
"""
import os
import sys

_APP = os.path.join(
    os.path.dirname(__file__), "..",
    "bd_platform_cloud_gemini_v1 2", "backend", "app",
)
sys.path.insert(0, os.path.abspath(_APP))

from common import relevance  # noqa: E402
from stage_map import (  # noqa: E402
    map_iati_stage, map_aiib_stage, map_wb_stage,
)

# Titre batiment fort et actionnable : score de base largement >= 8
# (mot-cle STRONG "structural" + type de marche "works").
TITRE = "Construction supervision and structural design for a new hospital"


def _statut(stage):
    return relevance(title=TITRE, procurement_type="works", stage=stage)[1]


# ---------------- Invariant de base sur le libelle de stage ----------------
def test_pipeline_conserve():
    assert _statut("pipeline") == "kept"
    assert _statut("identification") == "kept"


def test_execution_et_attribue_filtres():
    for s in ("execution", "awarded", "ongoing", "under construction", "signed"):
        assert _statut(s) == "filtered", s


def test_closed_et_cancelled_filtres():
    for s in ("closed", "completed", "cancelled", "terminated"):
        assert _statut(s) == "filtered", s


# ------------- Chainage stage_map -> relevance : pas de fuite --------------
def test_iati_terminaux_filtres():
    # 2=Implementation, 3/4=closed, 5=cancelled, 6=Suspended->execution
    for code in ("2", "3", "4", "5", "6"):
        assert _statut(map_iati_stage(code)) == "filtered", code
    assert _statut(map_iati_stage("1")) == "kept"  # Pipeline


def test_aiib_terminaux_filtres():
    assert _statut(map_aiib_stage("Approved")) == "filtered"
    assert _statut(map_aiib_stage("Terminated / Cancelled")) == "filtered"
    assert _statut(map_aiib_stage("Proposed")) == "kept"


def test_wb_terminaux_filtres():
    for s in ("Active", "Implementation", "Closed", "Completed", "Dropped", "Legacy"):
        assert _statut(map_wb_stage(s)) == "filtered", s
    assert _statut(map_wb_stage("Pipeline")) == "kept"


# --------- Contrat critique : defaut conservateur = toujours filtre --------
def test_defauts_conservateurs_filtrent():
    # Statut source inconnu -> stage_map renvoie "closed" -> relevance filtre.
    assert _statut(map_iati_stage("99")) == "filtered"
    assert _statut(map_aiib_stage("Statut inconnu")) == "filtered"
    assert _statut(map_wb_stage("statut inconnu")) == "filtered"
