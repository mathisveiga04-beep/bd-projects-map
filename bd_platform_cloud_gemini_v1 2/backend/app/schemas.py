from typing import Optional
from pydantic import BaseModel, ConfigDict


class ProjectBase(BaseModel):
    title: str
    description: str = ""
    country: str = "Cambodia"
    city: str = ""
    address: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_localized: bool = False
    sector: str = ""
    project_type: str = "Project"
    status: str = "identified"
    priority: str = "medium"
    color: str = "#F59E0B"
    source: str = "Manual"
    source_url: str = ""
    funder: str = ""
    estimated_budget: str = ""
    deadline: str = ""
    reliability: str = "medium"
    confidence: str = "medium"
    opportunity_size: str = "unknown"
    scope_summary: str = ""
    ai_summary: str = ""
    ai_recommendation: str = "watch"
    contributor: str = "system"


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(ProjectBase):
    title: Optional[str] = None


class ProjectOut(ProjectBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


class TenderBase(BaseModel):
    title: str
    country: str = "Cambodia"
    sector: str = ""
    funder: str = ""
    stage: str = "EOI"
    fit: str = "medium"
    estimated_budget: str = ""
    deadline: str = ""
    source_url: str = ""
    summary: str = ""
    ai_summary: str = ""
    ai_recommendation: str = "watch"


class TenderCreate(TenderBase):
    pass


class TenderUpdate(TenderBase):
    title: Optional[str] = None


class TenderOut(TenderBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


class AnalyzeRequest(BaseModel):
    title: str
    text: str
    source_url: str = ""


class ScraperRequest(BaseModel):
    source: Optional[str] = None
    dry_run: bool = False
