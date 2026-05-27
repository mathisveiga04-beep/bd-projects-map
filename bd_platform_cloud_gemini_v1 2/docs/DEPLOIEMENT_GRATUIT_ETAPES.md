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
5. Ajoute les variables : `DATABASE_URL`, `SUPABASE_JWT_SECRET`, `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `APP_SECRET`, `SCRAPER_API_KEY`, `GEMINI_API_KEY`, `GEMINI_MODEL`.
6. Teste `/health`.

## 5. Déployer le frontend
Option rapide : Vercel ou GitHub Pages.

Dans l'interface :
1. Ouvre les paramètres.
2. Renseigne l'URL Render du backend.
3. Clique `Tester API`.
4. Clique `Sync`.

## 6. Activer le scraping toutes les 4 heures
1. Dans GitHub > Settings > Secrets > Actions.
2. Ajoute `SCRAPER_API_KEY` avec la même valeur que Render.
3. Va dans Actions.
4. Lance `Opportunity Scraper` manuellement une première fois.
5. Vérifie que les nouveaux éléments apparaissent dans les alertes / opportunités non localisées.

## 7. Production propre
1. Domaine : connecter le domaine dans Vercel, puis vérifier HTTPS.
2. Variables Vercel : vérifier `SUPABASE_URL` et `SUPABASE_KEY` si elles sont utilisées côté frontend.
3. Sauvegarde Supabase : activer les backups disponibles ou exporter régulièrement le schéma et les tables critiques.
4. Sécurité : `APP_SECRET` protège les appels applicatifs, `SCRAPER_API_KEY` protège le cron, `SUPABASE_JWT_SECRET` protège les routes utilisateur/admin, `SUPABASE_SERVICE_ROLE_KEY` permet uniquement au backend Render de gérer les utilisateurs Supabase.
5. Démo : login `artelia2026`, carte, 42+ projets, alertes, lancement scraper manuel, analyse Gemini, export.

## 8. Workflow final
Scraper GitHub Actions → Backend Render → Gemini API → Supabase → Frontend HTML.
