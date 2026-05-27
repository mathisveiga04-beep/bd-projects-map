from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, UniqueConstraint
from .database import Base


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("title", "source_url", name="uq_project_title_source"),)

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(String(120), default="", index=True)
    owner_email = Column(String(255), default="")
    title = Column(String(255), nullable=False, index=True)
    description = Column(Text, default="")
    country = Column(String(80), default="Cambodia")
    city = Column(String(120), default="")
    address = Column(String(255), default="")
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    is_localized = Column(Boolean, default=False)
    sector = Column(String(180), default="")
    project_type = Column(String(120), default="Project")
    status = Column(String(80), default="identified")
    priority = Column(String(40), default="medium")
    color = Column(String(30), default="#F59E0B")
    source = Column(String(180), default="Manual")
    source_url = Column(Text, default="")
    funder = Column(String(180), default="")
    estimated_budget = Column(String(120), default="")
    deadline = Column(String(80), default="")
    reliability = Column(String(80), default="medium")
    confidence = Column(String(80), default="medium")
    opportunity_size = Column(String(80), default="unknown")
    scope_summary = Column(Text, default="")
    ai_summary = Column(Text, default="")
    ai_recommendation = Column(String(80), default="watch")
    contributor = Column(String(180), default="system")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Tender(Base):
    __tablename__ = "tenders"
    __table_args__ = (UniqueConstraint("title", "source_url", name="uq_tender_title_source"),)

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False, index=True)
    country = Column(String(80), default="Cambodia")
    sector = Column(String(180), default="")
    funder = Column(String(180), default="")
    stage = Column(String(80), default="EOI")
    fit = Column(String(80), default="medium")
    estimated_budget = Column(String(120), default="")
    deadline = Column(String(80), default="")
    source_url = Column(Text, default="")
    summary = Column(Text, default="")
    ai_summary = Column(Text, default="")
    ai_recommendation = Column(String(80), default="watch")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ScraperRun(Base):
    __tablename__ = "scraper_runs"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String(120), default="all")
    status = Column(String(50), default="started")
    items_found = Column(Integer, default=0)
    items_saved = Column(Integer, default=0)
    message = Column(Text, default="")
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
