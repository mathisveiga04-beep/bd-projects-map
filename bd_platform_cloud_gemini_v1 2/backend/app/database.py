import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

# En production (Render definit automatiquement RENDER=true), il est dangereux de
# retomber silencieusement sur une base SQLite locale : le systeme de fichiers est
# ephemere et les ecritures seraient perdues sans aucune alerte. On echoue donc
# explicitement plutot que de laisser croire que tout fonctionne.
if not DATABASE_URL:
    if os.getenv("RENDER"):
        raise RuntimeError(
            "DATABASE_URL n'est pas defini en production. "
            "Configurez la variable d'environnement DATABASE_URL sur Render avant de demarrer."
        )
    # Developpement local uniquement : repli explicite et signale.
    DATABASE_URL = "sqlite:///./bd_intelligence.db"
    print("[database] ATTENTION: DATABASE_URL absent -> repli sur SQLite locale (dev uniquement).")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    pool_recycle=1800,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
