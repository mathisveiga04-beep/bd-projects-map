"""
Connecteurs PREPARES (niveau 1 bailleurs + niveau 2 portails nationaux).

Chaque fonction respecte le contrat fetch() -> list[RawTender]. Tant que la
logique reelle n'est pas branchee, elle renvoie [] : le run global reste vert
et la source apparait simplement comme "0 ligne" dans ao_ingest_runs.

Pour activer une source : remplacer le corps par les appels API/scraping
officiels (voir l'URL de reference dans la docstring), construire des RawTender
et appeler .finalize(). Aucune autre modification necessaire (deja enregistre
dans run.CONNECTORS et seede dans ao_sources).

RAPPEL SOURCES OFFICIELLES UNIQUEMENT — interdiction d'agregateurs commerciaux
(Global Tenders, TendersInfo, Bid Detail, Tender Tiger, Tender News, ...).
"""
from __future__ import annotations
from .common import RawTender  # noqa: F401  (utilise par les implementations futures)


def _todo(source: str) -> list[RawTender]:
    print(f"[{source}] connecteur prepare mais pas encore branche -> 0 ligne.")
    return []


# ----------------------- Niveau 1 : bailleurs multilateraux -----------------
def adb_fetch() -> list[RawTender]:
    """ADB — Project/Consulting Procurement Notices.
    Ref : https://www.adb.org/projects/tenders  + Operational Procurement DB."""
    return _todo("ADB")


def aiib_fetch() -> list[RawTender]:
    """AIIB — Project Procurement Opportunities.
    Ref : https://www.aiib.org/en/opportunities/business/project-procurement/"""
    return _todo("AIIB")


def afd_fetch() -> list[RawTender]:
    """AFD — appels d'offres (KH, VN, LA, PH, ID).
    Ref : https://www.afd.fr/en/appels-offres"""
    return _todo("AFD")


def jica_fetch() -> list[RawTender]:
    """JICA — procurement / consultant notices (KH, VN, PH, ID, LA, MM, TH).
    Ref : https://www2.jica.go.jp/en/announce/"""
    return _todo("JICA")


# ----------------------- Niveau 2 : portails nationaux ----------------------
def philgeps_fetch() -> list[RawTender]:
    """Philippines — PhilGEPS (DPWH, DOTr, BCDA, MWSS). EN.
    Ref : https://www.philgeps.gov.ph/"""
    return _todo("PHILGEPS")


def gebiz_fetch() -> list[RawTender]:
    """Singapour — GeBIZ (BCA, HDB, PUB, LTA, JTC, Changi). EN. + data.gov.sg.
    Ref : https://www.gebiz.gov.sg/"""
    return _todo("GEBIZ")


def vneps_fetch() -> list[RawTender]:
    """Vietnam — VNEPS / National e-Procurement (MPI, MoC). VI+EN.
    Ref : https://muasamcong.mpi.gov.vn/"""
    return _todo("VNEPS")


def egp_th_fetch() -> list[RawTender]:
    """Thailande — e-GP (Comptroller General, MoT, EGAT, MRTA). TH (traduction).
    Ref : http://www.gprocurement.go.th/"""
    return _todo("EGP_TH")


def myproc_fetch() -> list[RawTender]:
    """Malaisie — MyProcurement / ePerolehan (MoF, JKR, MRT Corp). EN.
    Ref : https://myprocurement.treasury.gov.my/"""
    return _todo("MYPROC")


def inaproc_fetch() -> list[RawTender]:
    """Indonesie — INAPROC / LKPP (reseau LPSE, Ministry of Public Works). ID.
    Ref : https://inaproc.id/"""
    return _todo("INAPROC")


def mef_kh_fetch() -> list[RawTender]:
    """Cambodge — MEF / GDPP (MPWT, MoWRAM, PPWSA). KH+EN.
    Ref : https://www.gdpp.gov.kh/"""
    return _todo("MEF_KH")
