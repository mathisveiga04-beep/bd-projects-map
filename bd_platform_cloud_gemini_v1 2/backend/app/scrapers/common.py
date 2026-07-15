from dataclasses import dataclass
from typing import Optional


@dataclass
class Opportunity:
    title: str
    text: str
    source: str
    source_url: str = ""
    funder: str = ""
    country: str = "Cambodia"
    city: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    official_status: str = ""
