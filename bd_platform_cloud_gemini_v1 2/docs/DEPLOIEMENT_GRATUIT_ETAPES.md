# Déploiement gratuit — étapes concrètes

## 1. Créer un GitHub privé
1. Crée un repository privé.
2. Envoie tout le dossier `bd_platform_cloud_gemini_v1`.
3. Vérifie que `.env` n'est jamais poussé.

## 2. Créer la base Supabase
1. Crée un projet Supabase.
2. Récupère la connection string PostgreSQL.
3. Mets-la dans `DATABASE_URL` côté Render.
4. Optionnel : colle `database/supabase_schema.sql` dans SQL Editor.

## 3. Créer la clé Gemini
1. Va sur Google AI Studio.
2. Crée une clé API.
3. Mets-la dans Render sous `GEMINI_API_KEY`.

## 4. Déployer le backend sur Render
1. New Web Service.
2. Connecte le repo GitHub.
3. Build command : `pip install -r backend/requirements.txt`
4. Start command : `cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. Ajoute les variables : `DATABASE_URL`, `GEMINI_API_KEY`, `GEMINI_MODEL`.
6. Teste `/health`.

## 5. Déployer le frontend
Option rapide : Vercel ou GitHub Pages.

Dans l'interface :
1. Ouvre les paramètres.
2. Renseigne l'URL Render du backend.
3. Clique `Tester API`.
4. Clique `Sync`.

## 6. Activer le scraping quotidien
1. Dans GitHub > Settings > Secrets > Actions.
2. Ajoute `BACKEND_URL=https://ton-api.onrender.com`.
3. Va dans Actions.
4. Lance `Daily opportunity scraper` manuellement une première fois.

## 7. Workflow final
Scraper GitHub Actions → Backend Render → Gemini API → Supabase → Frontend HTML.
