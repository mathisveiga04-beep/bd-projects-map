# Architecture cible

## Rôle de chaque bloc

- Frontend HTML : affichage carte, détails, filtres, création manuelle, sync.
- FastAPI : API centrale, sécurité future, synchronisation.
- Supabase/PostgreSQL : stockage des projets, tenders, runs scraper.
- Scrapers : récupération automatique des opportunités.
- Gemini : qualification IA et extraction JSON.
- GitHub Actions : déclenchement quotidien.

## Pourquoi l'IA ne scrape pas directement

L'IA analyse les données. Les scrapers collectent les pages, flux RSS et API. Cette séparation est plus fiable, plus économique et plus maintenable.

## Champs IA retournés

- summary
- sector
- project_type
- city
- country
- funder
- estimated_budget
- deadline
- confidence
- opportunity_size
- priority
- recommendation
- scope_summary
