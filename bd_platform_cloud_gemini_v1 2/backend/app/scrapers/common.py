from dataclasses import dataclass

@dataclass
class Opportunity:
    title: str
    text: str
    source: str
    source_url: str = ""
    funder: str = ""
    country: str = "Cambodia"
