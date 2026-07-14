"""
Runner d'ingestion RELATIONNEL : connecteur -> filtre/normalise -> upsert du
GRAPHE (organisations -> projets -> AO -> liens de roles) -> journalise.

Ordre d'upsert (respecte les cles etrangeres) :
  1. ao_organisations  (financeurs, autorites, ministeres)
  2. ao_projects       (rattaches a leur financeur)
  3. ao_tenders        (rattaches projet/financeur/autorite) -> renvoie les id
  4. ao_party_roles    (qui joue quel role sur quel AO)

Identifiants entites = UUID deterministes (common.py) -> idempotent, sans
aller-retour. Les tender_id (bigint auto) sont recuperes via return=representation.

Variables d'env (deja sur Render) :
  SUPABASE_URL                (defaut : projet BD Projects Map)
  SUPABASE_SERVICE_ROLE_KEY   cle service-role (ecriture)

Usage CLI : python -m app.ao_ingest.run WB
"""
from __future__ import annotations
import json
import os
import sys
import time
import urllib.request
from typing import Callable

from .common import RawTender, dedupe
from . import worldbank
from . import connectors_stub as stubs

# Registre des connecteurs (un module/fonction par source).
# WB est operationnel ; les autres sont prepares (stubs) et renvoient [] tant
# que leur connecteur n'est pas branche -> le run reste vert.
CONNECTORS: dict[str, Callable[[], list[RawTender]]] = {
    "WB":       worldbank.fetch,
    "ADB":      stubs.adb_fetch,
    "AIIB":     stubs.aiib_fetch,
    "AFD":      stubs.afd_fetch,
    "JICA":     stubs.jica_fetch,
    "PHILGEPS": stubs.philgeps_fetch,
    "GEBIZ":    stubs.gebiz_fetch,
    "VNEPS":    stubs.vneps_fetch,
    "EGP_TH":   stubs.egp_th_fetch,
    "MYPROC":   stubs.myproc_fetch,
    "INAPROC":  stubs.inaproc_fetch,
    "MEF_KH":   stubs.mef_kh_fetch,
}

SUPABASE_URL = (os.getenv("SUPABASE_URL")
                or "https://xyvsfkalaeatwmcobwrg.supabase.co").rstrip("/")
SERVICE_ROLE = os.getenv("SUPABASE_SERVICE_ROLE") or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


def _sb_request(method: str, path: str, body: bytes | None = None,
                prefer: str | None = None) -> tuple[int, str]:
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    headers = {
        "apikey": SERVICE_ROLE,
        "Authorization": f"Bearer {SERVICE_ROLE}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.status, resp.read().decode("utf-8")


def _upsert(table_conflict: str, rows: list[dict], prefer: str) -> tuple[int, str]:
    if not rows:
        return 204, "[]"
    body = json.dumps(rows, default=str).encode("utf-8")
    return _sb_request("POST", table_conflict, body=body, prefer=prefer)


def _dedupe_by_id(rows: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    for r in rows:
        seen[r["id"]] = r
    return list(seen.values())


def upsert_graph(records: list[RawTender]) -> dict:
    """Upsert idempotent du graphe complet. Retourne des compteurs par table."""
    if not records:
        return {"organisations": 0, "projects": 0, "tenders": 0, "roles": 0}

    # 1. Organisations (financeurs / autorites / ministeres)
    orgs = _dedupe_by_id([o for r in records for o in r.organisations()])
    _upsert("ao_organisations?on_conflict=id", orgs,
            "resolution=merge-duplicates,return=minimal")

    # 2. Projets
    projects = _dedupe_by_id([p for r in records if (p := r.project())])
    _upsert("ao_projects?on_conflict=id", projects,
            "resolution=merge-duplicates,return=minimal")

    # 3. AO (tenders) -> on recupere les id (bigint) pour cabler les roles
    tender_rows = []
    for r in records:
        row = r.tender_row()
        row["raw"] = r.raw
        tender_rows.append(row)
    status, payload = _upsert(
        "ao_tenders?on_conflict=source_code,external_ref&select=id,source_code,external_ref",
        tender_rows, "resolution=merge-duplicates,return=representation",
    )
    ref_to_id: dict[tuple[str, str], int] = {}
    try:
        for row in json.loads(payload):
            ref_to_id[(row["source_code"], row["external_ref"])] = row["id"]
    except Exception:
        pass

    # 4. Liens de roles (qui joue quel role sur quel AO)
    role_rows = []
    for r in records:
        tid = ref_to_id.get((r.source_code, r.external_ref))
        puid = None
        if r.project_ref:
            from .common import project_uid
            puid = project_uid(r.source_code, r.project_ref)
        for role in r.party_roles():
            role["tender_id"] = tid
            role["project_uid"] = puid
            role_rows.append(role)
    role_rows = _dedupe_by_id(role_rows)
    _upsert("ao_party_roles?on_conflict=id", role_rows,
            "resolution=merge-duplicates,return=minimal")

    return {"organisations": len(orgs), "projects": len(projects),
            "tenders": len(tender_rows), "roles": len(role_rows)}


def log_run(source: str, status: str, fetched: int, upserted: int, rejected: int, err: str | None):
    body = json.dumps([{
        "source_code": source, "status": status, "rows_fetched": fetched,
        "rows_upserted": upserted, "rows_rejected": rejected,
        "error_message": err, "finished_at": "now()",
    }]).encode("utf-8")
    try:
        _sb_request("POST", "ao_ingest_runs", body=body, prefer="return=minimal")
    except Exception as e:
        print(f"[run] log_run failed: {e}")


def run_source(source: str) -> dict:
    fetch = CONNECTORS.get(source)
    if not fetch:
        raise SystemExit(f"Connecteur inconnu: {source}")
    t0 = time.time()
    fetched = rejected = 0
    counts = {"organisations": 0, "projects": 0, "tenders": 0, "roles": 0}
    status = "ok"
    err = None
    try:
        records = fetch()
        fetched = len(records)
        kept = [r for r in records
                if r.relevance_status == "kept" and r.verification_status == "verified"]
        rejected = fetched - len(kept)
        kept = dedupe(kept)
        counts = upsert_graph(kept)
    except Exception as e:
        status = "error"
        err = str(e)
        print(f"[run] {source} ERROR: {e}")
    _up = counts.get("tenders", 0)
    if status == "ok" and _up == 0:
        print(f"[SCRAPER][WARN] {source} : 0 opportunite retenue (fetched={fetched}, rejected={rejected}) -- source potentiellement cassee ou filtree a 100%")
    else:
        print(f"[SCRAPER] {source} : fetched={fetched} upserted={_up} rejected={rejected} status={status}")
    log_run(source, status, fetched, counts.get("tenders", 0), rejected, err)
    return {"source": source, "status": status, "fetched": fetched,
            "rejected": rejected, "upserted": counts,
            "seconds": round(time.time() - t0, 1), "error": err}


def run_all(sources: list[str] | None = None) -> list[dict]:
    """Lance plusieurs sources d'affilee (un echec n'arrete pas les suivantes)."""
    srcs = sources or list(CONNECTORS.keys())
    return [run_source(s) for s in srcs]


if __name__ == "__main__":
    if not SUPABASE_URL or not SERVICE_ROLE:
        raise SystemExit("SUPABASE_URL et SUPABASE_SERVICE_ROLE_KEY doivent etre definis.")
    arg = sys.argv[1] if len(sys.argv) > 1 else "WB"
    if arg.upper() == "ALL":
        print(json.dumps(run_all(), indent=2, ensure_ascii=False))
    else:
        print(json.dumps(run_source(arg), indent=2, ensure_ascii=False))
