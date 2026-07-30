from typing import Optional
from pydantic import BaseModel, ConfigDict, field_validator


class ProjectBase(BaseModel):
    owner_id: str = ""
    owner_email: str = ""
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
    project_status: str = ""  # statut cycle de vie (IA): Demarre/En attente/En cours/Termine/Annule
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

    @field_validator(
        "owner_id", "owner_email", "title", "description", "country", "city",
        "address", "sector", "project_type", "status", "project_status",
        "priority", "color", "source", "source_url", "funder",
        "estimated_budget", "deadline", "reliability", "confidence",
        "opportunity_size", "scope_summary", "ai_summary", "ai_recommendation",
        "contributor",
        mode="before",
    )
    @classmethod
    def _none_to_empty_str(cls, v):
        """Les colonnes nullables en base peuvent renvoyer NULL ; on les normalise en chaine vide pour la sortie."""
        return "" if v is None else v


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


class GenerateRequest(BaseModel):
    prompt: str
    max_tokens: int = 700
    mode: str = "general"


class ScraperRequest(BaseModel):
    source: Optional[str] = None
    dry_run: bool = False
    limit: int = 10  # nb max d opportunites analysees par run (evite les timeouts Render)
