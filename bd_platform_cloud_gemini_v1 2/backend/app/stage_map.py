"""Source unique de verite pour la traduction statut -> stage.

Centralise ici pour eviter la classe de bugs de fuite : un statut inattendu
qui tombe sur un defaut trop permissif (ex. "open" ou "pipeline") et se
retrouve conserve a tort. Chaque mapping est couvert par tests/test_stage_map.py.

Regle metier : seuls les projets en "pipeline" (preparation / en attente de
reponse) sont conserves en aval par relevance(). Tout le reste
(execution / awarded / closed / cancelled) est exclu. Le defaut doit donc
etre CONSERVATEUR (exclusion) -- jamais "open" ni "pipeline".
"""

# --- IATI / d-portal (ADB, AFD, JICA) ---
# 1=Pipeline/identification, 2=Implementation, 3=Finalisation,
# 4=Closed, 5=Cancelled, 6=Suspended
IATI_STATUS_STAGE = {
    "1": "pipeline",
    "2": "execution",
    "3": "closed",
    "4": "closed",
    "5": "cancelled",
    "6": "execution",
}
IATI_STAGE_DEFAULT = "closed"


def map_iati_stage(code) -> str:
    return IATI_STATUS_STAGE.get(str(code), IATI_STAGE_DEFAULT)


# --- AIIB (tableau JS de la page projets) ---
AIIB_STATUS_STAGE = {
    "Proposed": "pipeline",
    "Approved": "awarded",
    "Terminated / Cancelled": "cancelled",
    "Dropped": "cancelled",
}
AIIB_STAGE_DEFAULT = "closed"


def map_aiib_stage(status) -> str:
    return AIIB_STATUS_STAGE.get((status or "").strip(), AIIB_STAGE_DEFAULT)


# --- World Bank (libelle texte libre) ---
def map_wb_stage(status) -> str:
    s = (status or "").lower()
    if "pipeline" in s or "concept" in s or "identif" in s or "prepar" in s:
        return "pipeline"
    if "active" in s or "implementation" in s or "execution" in s:
        return "execution"
    if "closed" in s or "completed" in s:
        return "closed"
    if "dropped" in s or "cancel" in s or "legacy" in s:
        return "cancelled"
    return "closed"
