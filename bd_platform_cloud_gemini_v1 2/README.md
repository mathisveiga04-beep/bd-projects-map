# B&D Projects Map — Production-ready starter

Plateforme Business Development pour Artelia Cambodia : carte projets, veille opportunités, backend FastAPI, base Supabase/PostgreSQL, IA Gemini et scraper automatisable.

## Contenu

- `frontend/index.html` : application HTML prête à héberger.
- `backend/` : API FastAPI.
- `database/supabase_schema.sql` : schéma Supabase/PostgreSQL.
- `.github/workflows/daily-scraper.yml` : automatisation quotidienne du scraper.
- `GUIDE_CREATION_EN_LIGNE.md` : guide complet de mise en ligne.

## Lancement local rapide

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Puis ouvrir :

```txt
http://127.0.0.1:8000/health
```

## Variables principales

```txt
DATABASE_URL=
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.0-flash
SCRAPER_API_KEY=
RSS_SOURCES=
```

## Sécurité scraper

Si `SCRAPER_API_KEY` est renseignée côté backend, l’appel `/scraper/run` doit inclure :

```txt
X-API-Key: ta_cle
```

Le workflow GitHub Actions est déjà configuré pour envoyer cette clé via secret GitHub.
