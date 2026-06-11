"""
Sous-package "Appels d'offre ASEAN" (ao = appels d'offre).

Auto-suffisant : ne touche a rien de l'app existante.
- common.py    : schema normalise + filtre batiment + scoring + dedup
- worldbank.py : connecteur Banque Mondiale (source 'WB')
- run.py       : runner d'ingestion -> upsert Supabase (tables ao_*)
- api.py       : routeur FastAPI, prefixe /ao (n'entre PAS en conflit avec /tenders)

A brancher dans app/main.py :
    from .ao_ingest.api import router as ao_router
    app.include_router(ao_router)
"""
