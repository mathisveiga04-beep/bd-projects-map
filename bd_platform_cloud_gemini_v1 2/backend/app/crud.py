from sqlalchemy.orm import Session
from . import models, schemas


def list_projects(db: Session):
    return db.query(models.Project).order_by(models.Project.updated_at.desc()).all()


def _clean_key(value: str | None) -> str:
    return " ".join((value or "").strip().lower().split())


def _find_project_match(db: Session, data: schemas.ProjectCreate):
    title = _clean_key(data.title)
    source_url = _clean_key(data.source_url)
    query = db.query(models.Project).filter(models.Project.title == data.title)
    if source_url:
        found = query.filter(models.Project.source_url == data.source_url).first()
        if found:
            return found
    for obj in query.limit(20).all():
        if _clean_key(obj.title) == title and _clean_key(obj.source_url) == source_url:
            return obj
    if not source_url and data.latitude is not None and data.longitude is not None:
        for obj in query.limit(20).all():
            if obj.latitude is None or obj.longitude is None:
                continue
            if abs(float(obj.latitude) - float(data.latitude)) < 0.0001 and abs(float(obj.longitude) - float(data.longitude)) < 0.0001:
                return obj
    return None


find_project_match = _find_project_match


def create_or_update_project(db: Session, data: schemas.ProjectCreate):
    """Retourne (projet, created) ; created=False si fusion dans un projet existant."""
    existing = _find_project_match(db, data)
    if existing:
        update_project(db, existing.id, schemas.ProjectUpdate(**data.model_dump()))
        return db.get(models.Project, existing.id), False
    obj = models.Project(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj, True


def create_project(db: Session, data: schemas.ProjectCreate):
    obj, _created = create_or_update_project(db, data)
    return obj


def update_project(db: Session, project_id: int, data: schemas.ProjectUpdate):
    obj = db.get(models.Project, project_id)
    if not obj:
        return None
    for k, v in data.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


def delete_project(db: Session, project_id: int):
    obj = db.get(models.Project, project_id)
    if not obj:
        return False
    db.delete(obj)
    db.commit()
    return True


def list_tenders(db: Session):
    return db.query(models.Tender).order_by(models.Tender.updated_at.desc()).all()


def _find_tender_match(db: Session, data: schemas.TenderCreate):
    title = _clean_key(data.title)
    source_url = _clean_key(data.source_url)
    query = db.query(models.Tender).filter(models.Tender.title == data.title)
    if source_url:
        found = query.filter(models.Tender.source_url == data.source_url).first()
        if found:
            return found
    for obj in query.limit(20).all():
        if _clean_key(obj.title) == title and _clean_key(obj.source_url) == source_url:
            return obj
    return None


def create_tender(db: Session, data: schemas.TenderCreate):
    existing = _find_tender_match(db, data)
    if existing:
        for k, v in data.model_dump().items():
            if v is not None:
                setattr(existing, k, v)
        db.commit()
        db.refresh(existing)
        return existing
    obj = models.Tender(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj
