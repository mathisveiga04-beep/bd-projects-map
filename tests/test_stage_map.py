"""Tests de non-regression du mapping statut -> stage (stage_map.py).

Ces tests verrouillent la regle metier : seuls les projets en "pipeline"
sont conserves ; tout statut inattendu doit tomber sur un defaut CONSERVATEUR
(jamais "open" ni "pipeline"). Ils couvrent les 3 bugs de fuite corriges
(IATI 2/6, WB Active/Legacy, AIIB defaut) + le defaut IATI open->closed.
"""
import os
import sys

_APP = os.path.join(
    os.path.dirname(__file__), "..",
    "bd_platform_cloud_gemini_v1 2", "backend", "app",
)
sys.path.insert(0, os.path.abspath(_APP))

from stage_map import (  # noqa: E402
    map_iati_stage, map_aiib_stage, map_wb_stage,
    IATI_STAGE_DEFAULT, AIIB_STAGE_DEFAULT,
)


# ------------------------------- IATI ---------------------------------
def test_iati_pipeline_conserve():
    assert map_iati_stage("1") == "pipeline"


def test_iati_implementation_et_suspendu_exclus():
    # bug corrige : 2 (Implementation) et 6 (Suspended) fuyaient en "open"
    assert map_iati_stage("2") == "execution"
    assert map_iati_stage("6") == "execution"


def test_iati_closed_cancelled():
    assert map_iati_stage("3") == "closed"
    assert map_iati_stage("4") == "closed"
    assert map_iati_stage("5") == "cancelled"


def test_iati_defaut_conservateur():
    # bug latent corrige : le defaut etait "open" (fuite)
    assert IATI_STAGE_DEFAULT == "closed"
    for bad in ("99", "", "x", None):
        assert map_iati_stage(bad) == "closed"
        assert map_iati_stage(bad) not in ("open", "pipeline")


# ------------------------------- AIIB ---------------------------------
def test_aiib_proposed_conserve():
    assert map_aiib_stage("Proposed") == "pipeline"


def test_aiib_approuve_exclu():
    assert map_aiib_stage("Approved") == "awarded"


def test_aiib_cancelled():
    assert map_aiib_stage("Terminated / Cancelled") == "cancelled"
    assert map_aiib_stage("Dropped") == "cancelled"


def test_aiib_defaut_conservateur():
    # bug corrige : le defaut etait "pipeline" (fuite des statuts inconnus)
    assert AIIB_STAGE_DEFAULT == "closed"
    for bad in ("Completed", "Under Implementation", "", None):
        assert map_aiib_stage(bad) == "closed"
        assert map_aiib_stage(bad) not in ("open", "pipeline")


# ---------------------------- World Bank ------------------------------
def test_wb_pipeline():
    assert map_wb_stage("Pipeline") == "pipeline"
    assert map_wb_stage("Concept") == "pipeline"


def test_wb_active_et_implementation_exclus():
    # bug (regression) corrige : Active/Implementation fuyaient en "open"
    assert map_wb_stage("Active") == "execution"
    assert map_wb_stage("Implementation") == "execution"
    assert map_wb_stage("Active") != "open"


def test_wb_closed_et_cancelled():
    assert map_wb_stage("Closed") == "closed"
    assert map_wb_stage("Completed") == "closed"
    assert map_wb_stage("Dropped") == "cancelled"
    assert map_wb_stage("Legacy") == "cancelled"


def test_wb_defaut_conservateur():
    for bad in ("", None, "statut inattendu"):
        assert map_wb_stage(bad) == "closed"
        assert map_wb_stage(bad) not in ("open", "pipeline")
