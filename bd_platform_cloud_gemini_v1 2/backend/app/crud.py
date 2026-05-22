from sqlalchemy.orm import Session
from . import models, schemas


def list_projects(db: Session):
    return db.query(models.Project).order_by(models.Project.updated_at.desc()).all()


def create_project(db: Session, data: schemas.ProjectCreate):
    obj = models.Project(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
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


def create_tender(db: Session, data: schemas.TenderCreate):
    obj = models.Tender(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj
