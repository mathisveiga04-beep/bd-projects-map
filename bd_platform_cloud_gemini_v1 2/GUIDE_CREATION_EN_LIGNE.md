# Guide de création en ligne — B&D Projects Map

Objectif : mettre en ligne la plateforme B&D Projects Map avec un frontend HTML, un backend FastAPI, une base Supabase, une IA Gemini et un scraper automatique.

## 1. Architecture finale

- Frontend : Vercel ou GitHub Pages
- Backend API : Render
- Base de données : Supabase PostgreSQL
- IA : Google Gemini API
- Scraper : GitHub Actions qui appelle le backend chaque jour

## 2. Créer le repository GitHub

1. Aller sur GitHub.
2. Créer un nouveau repository, par exemple : `bd-projects-map`.
3. Uploader tout le contenu de ce dossier dans le repository.
4. Vérifier que les dossiers suivants sont présents :
   - `frontend/index.html`
   - `backend/app/main.py`
   - `backend/requirements.txt`
   - `database/supabase_schema.sql`
   - `.github/workflows/daily-scraper.yml`

## 3. Créer la base Supabase

1. Aller sur Supabase.
2. Créer un nouveau projet.
3. Aller dans `SQL Editor`.
4. Ouvrir le fichier `database/supabase_schema.sql`.
5. Copier-coller le contenu dans Supabase.
6. Cliquer sur `Run`.
7. Aller dans `Project Settings > Database`.
8. Copier l’URL PostgreSQL sous la forme :

```txt
postgresql://postgres:[PASSWORD]@db.[PROJECT_REF].supabase.co:5432/postgres
```

Pour Render, utiliser plutôt :

```txt
postgresql+psycopg2://postgres:[PASSWORD]@db.[PROJECT_REF].supabase.co:5432/postgres
```

## 4. Créer la clé Gemini

1. Aller sur Google AI Studio.
2. Créer une clé API Gemini.
3. Garder cette clé pour Render.
4. Modèle conseillé au départ :

```txt
gemini-2.0-flash
```

## 5. Déployer le backend sur Render

1. Aller sur Render.
2. Créer un nouveau `Web Service`.
3. Connecter le repository GitHub.
4. Choisir le dossier racine du repository.
5. Configuration :

```txt
Environment: Python
Build Command: pip install -r backend/requirements.txt
Start Command: cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

6. Ajouter les variables d’environnement :

```txt
APP_ENV=production
DATABASE_URL=postgresql+psycopg2://postgres:[PASSWORD]@db.[PROJECT_REF].supabase.co:5432/postgres
GEMINI_API_KEY=ta_cle_gemini
GEMINI_MODEL=gemini-2.0-flash
SCRAPER_API_KEY=une_cle_longue_aleatoire
RSS_SOURCES=https://example.com/feed.xml
```

7. Déployer.
8. Tester l’URL :

```txt
https://ton-backend-render.onrender.com/health
```

Réponse attendue :

```json
{"status":"ok","database":"connected"}
```

## 6. Déployer le frontend

Option simple recommandée : Vercel.

1. Aller sur Vercel.
2. Importer le repository GitHub.
3. Définir le dossier frontend comme dossier de publication si demandé.
4. Vérifier que `frontend/index.html` est bien servi.
5. Une fois le site ouvert, entrer le mot de passe de l’application.
6. Aller dans les réglages API de l’interface.
7. Renseigner l’URL Render du backend :

```txt
https://ton-backend-render.onrender.com
```

8. Cliquer sur `Tester API`.
9. Cliquer sur `Charger depuis PostgreSQL` pour synchroniser.

## 7. Configurer le scraper automatique GitHub Actions

Dans GitHub :

1. Aller dans `Settings > Secrets and variables > Actions`.
2. Ajouter ces secrets :

```txt
BACKEND_URL=https://ton-backend-render.onrender.com
SCRAPER_API_KEY=la_meme_cle_que_sur_render
```

3. Aller dans `Actions`.
4. Ouvrir `Daily opportunity scraper`.
5. Cliquer sur `Run workflow` pour tester.
6. Ensuite, le scraper se lancera automatiquement tous les jours à 07h30 heure Cambodge.

## 8. Vérifications finales

À vérifier dans l’ordre :

1. `/health` répond correctement.
2. Le frontend s’ouvre en ligne.
3. Le frontend arrive à tester l’API.
4. Un projet créé dans le frontend apparaît dans Supabase.
5. GitHub Actions peut lancer le scraper.
6. Les opportunités détectées apparaissent dans l’onglet veille/projets.

## 9. Limites actuelles du MVP

- Le scraper actuel est une première base : World Bank + RSS.
- LinkedIn/Facebook ne doivent pas être scrapés directement sans API ou autorisation adaptée.
- Render gratuit peut mettre le backend en sommeil après inactivité.
- Gemini bascule sur une analyse simple si la clé API est absente ou si l’appel échoue.

## 10. Priorités après mise en ligne

1. Ajouter des sources RSS fiables : AFD, World Bank, ADB, UNDP, JICA, presse locale.
2. Ajouter une page admin plus sécurisée.
3. Ajouter un historique des opportunités détectées.
4. Ajouter une déduplication plus stricte des opportunités.
5. Ajouter une notification email ou Telegram quand une opportunité est détectée.
