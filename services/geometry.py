import math
from datetime import datetime
from pyproj import Transformer
from shapely.geometry import shape, mapping, Polygon, MultiPolygon
from shapely.ops import transform

TO_METERS = Transformer.from_crs(4326, 3035, always_xy=True).transform
TO_WGS84 = Transformer.from_crs(3035, 4326, always_xy=True).transform

def timestamp(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timestamp must include UTC offset")
    return result

def polygon(value):
    if value.get("type") == "Feature":
        value = value["geometry"]
    geom = shape(value)
    if not isinstance(geom, (Polygon, MultiPolygon)) or geom.is_empty or not geom.is_valid:
        raise ValueError("Valid nonempty Polygon or MultiPolygon required")
    w, s, e, n = geom.bounds
    if not all(math.isfinite(x) for x in geom.bounds) or not (5 <= w <= e <= 16 and 46 <= s <= n <= 56):
        raise ValueError("Boundary outside Germany pilot region (5–16 E,46–56 N)")
    if len(geom.wkb) > 1_000_000:
        raise ValueError("Boundary too detailed")
    return geom

def measure(geometry):
    geom = polygon(geometry)
    projected = transform(TO_METERS, geom)
    parts = list(projected.geoms) if isinstance(projected, MultiPolygon) else [projected]
    return {"geometry": mapping(geom), "burned_area_ha": projected.area / 10000, "enclosed_area_ha": sum(Polygon(p.exterior).area for p in parts) / 10000, "area_crs": "EPSG:3035"}

def compare(old, new):
    unavailable = {"status": "insufficient_evidence", "message": "Bewegung kann nicht bestimmt werden."}
    if old.get("review_state") != "approved" or new.get("review_state") != "approved":
        return unavailable
    if timestamp(new["acquired_at"]) <= timestamp(old["acquired_at"]) or old.get("footprint_kind") != new.get("footprint_kind"):
        return unavailable
    if not old.get("coverage") or not new.get("coverage"):
        return unavailable
    coverage_old, coverage_new = polygon(old["coverage"]), polygon(new["coverage"])
    if not coverage_old.equals(coverage_new):
        return unavailable
    a, b = (transform(TO_METERS, polygon(x["geometry"])) for x in (old, new))
    if not coverage_old.covers(polygon(old["geometry"])) or not coverage_new.covers(polygon(new["geometry"])):
        return unavailable
    added, removed = b.difference(a), a.difference(b)
    if removed.area > max(100, a.area * .01):
        return {**unavailable, "reason": "Boundary contraction or correction; growth is ambiguous"}
    elapsed = (timestamp(new["acquired_at"]) - timestamp(old["acquired_at"])).total_seconds() / 3600
    center = a.centroid
    radius = max(b.bounds[2] - b.bounds[0], b.bounds[3] - b.bounds[1]) * 4 + center.distance(b.centroid) + 1000
    sectors = {}
    for i, name in enumerate(["N", "NE", "E", "SE", "S", "SW", "W", "NW"]):
        angles = [math.radians(i * 45 - 22.5 + j * 45 / 20) for j in range(21)]
        wedge = Polygon([(center.x, center.y)] + [(center.x + radius * math.sin(t), center.y + radius * math.cos(t)) for t in angles] + [(center.x, center.y)])
        sectors[name] = added.intersection(wedge).area / 10000
    dominant = max(sectors, key=sectors.get)
    share = sectors[dominant] / (added.area / 10000) if added.area else 0
    return {"status": "measured", "kind": "burned_footprint_change", "added_geometry": mapping(transform(TO_WGS84, added)) if not added.is_empty else None, "added_area_ha": added.area / 10000, "elapsed_hours": elapsed, "area_growth_ha_per_hour": added.area / 10000 / elapsed, "sectors_ha": sectors, "dominant_sector": dominant if share >= .4 else None, "message": "Gemessene Änderung der kartierten Fläche; keine Vorhersage der Feuerfront."}
