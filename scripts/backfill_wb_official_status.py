"""Correction historique : réaligne project_status des projets déjà stockés
sur le statut OFFICIEL de la source (World Bank projectstatusdisplay).

Contexte : jusqu'au correctif, project_status était deviné par Gemini. Ce
script relit le statut officiel via le scraper World Bank existant et met à
jour les projets correspondants (correspondance sur source_url, repli titre).

A lancer par un humain, depuis la racine du dépét, avec DATABASE_URL
défini et un accés réseau à l'API World Bank :

    # apercu (aucune ecriture)
    python "scripts/backfill_wb_official_status.py"

    # application reelle
    python "scripts/backfill_wb_official_status.py" --apply

Rien n'est supprimé : seule la colonne project_status peut etre mise à jour,
et uniquement lorsqu'un statut officiel est disponible.
"""
import os
import sys
import argparse

_BACKEND = os.path.join(
    os.path.dirname(__file__), "..",
    "bd_platform_cloud_gemini_v1 2", "backend",
)
sys.path.insert(0, os.path.abspath(_BACKEND))


def main():
    parser = argparse.ArgumentParser(
        description="Backfill du statut officiel World Bank vers project_status",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Applique les mises a jour (sinon simple apercu)",
    )
    args = parser.parse_args()

    from app.official_status import official_status_to_fr
    from app.scrapers.worldbank import scrape_world_bank_cambodia
    from app import models
    from app.database import get_db

    db = next(get_db())
    try:
        opportunities = scrape_world_bank_cambodia()
        planned = 0
        skipped = 0
        for opp in opportunities:
            fr = official_status_to_fr(getattr(opp, "official_status", ""))
            if not fr:
                skipped += 1
                continue
            url = getattr(opp, "source_url", "") or ""
            title = getattr(opp, "title", "") or ""
            proj = None
            if url:
                proj = (
                    db.query(models.Project)
                    .filter(models.Project.source_url == url)
                    .first()
                )
            if proj is None and title:
                proj = (
                    db.query(models.Project)
                    .filter(models.Project.title == title)
                    .first()
                )
            if proj is None or proj.project_status == fr:
                continue
            print("MAJ  %-12s -> %-12s  %s" % (proj.project_status, fr, title[:70]))
            if args.apply:
                proj.project_status = fr
                db.add(proj)
            planned += 1
        if args.apply:
            db.commit()
            print("\n%d projet(s) mis a jour." % planned)
        else:
            print("\nAPERCU : %d projet(s) seraient mis a jour (--apply pour appliquer)." % planned)
        print("%d opportunite(s) World Bank sans statut officiel exploitable." % skipped)
    finally:
        db.close()


if __name__ == "__main__":
    main()
