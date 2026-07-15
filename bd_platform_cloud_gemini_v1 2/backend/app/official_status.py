"""Traduction des statuts OFFICIELS de source vers les valeurs FR canoniques.

Isolé dans son propre module (comme stage_map.py) afin d'être testable sans
importer main.py, dont l'import déclenche une connexion base de données.

Régle métier : quand une source expose un statut officiel structuré
(ex. World Bank projectstatusdisplay), il est traduit ici vers une valeur FR
canonique et fait autorité sur l'analyse Gemini. Si le statut est absent ou
non reconnu, on renvoie une chaine vide et l'appelant retombe sur l'IA.
"""
import unicodedata

FR_EN_ATTENTE = "En attente"
FR_EN_COURS = "En cours"
FR_TERMINE = "Terminé"
FR_ANNULE = "Annulé"


def official_status_to_fr(value):
    """Traduit un statut OFFICIEL de source vers une valeur FR canonique.

    Retourne une chaine vide si le statut est absent ou non reconnu,
    auquel cas l'appelant conserve l'analyse IA.
    """
    raw = ("" if value is None else str(value)).strip().lower()
    raw = "".join(
        c for c in unicodedata.normalize("NFD", raw)
        if unicodedata.category(c) != "Mn"
    )
    if not raw:
        return ""
    if any(k in raw for k in ("pipeline", "concept", "identif", "prepar", "proposed", "planned", "en attente")):
        return FR_EN_ATTENTE
    if any(k in raw for k in ("active", "implementation", "execution", "ongoing", "disburs", "en cours")):
        return FR_EN_COURS
    if any(k in raw for k in ("closed", "completed", "complete", "terminated", "termine")):
        return FR_TERMINE
    if any(k in raw for k in ("dropped", "cancel", "abandon", "annul")):
        return FR_ANNULE
    return ""
