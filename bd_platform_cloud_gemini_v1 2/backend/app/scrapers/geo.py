import time
import requests

_CACHE = {}
_NOMINATIM = "https://nominatim.openstreetmap.org/search"


def geocode(country: str = "", city: str = "", address: str = ""):
    """Resolve (lat, lng) from a place via OpenStreetMap Nominatim.

    Returns (None, None) when nothing is found. Results are cached in
    memory and a 1s pause is respected per live call to honour the
    Nominatim usage policy (max 1 request/second).
    """
    parts = [p.strip() for p in (address, city, country) if p and p.strip()]
    query = ", ".join(parts)
    if not query:
        return None, None
    key = query.lower()
    if key in _CACHE:
        return _CACHE[key]
    lat = lng = None
    try:
        resp = requests.get(
            _NOMINATIM,
            params={"q": query, "format": "json", "limit": 1},
            headers={"User-Agent": "BD-Projects-Map/1.0 (Artelia BD monitoring)"},
            timeout=15,
        )
        data = resp.json()
        if isinstance(data, list) and data:
            lat = float(data[0]["lat"])
            lng = float(data[0]["lon"])
        time.sleep(1)
    except Exception as exc:
        print("Geocoding failed for " + query + ": " + str(exc))
    _CACHE[key] = (lat, lng)
    return lat, lng

