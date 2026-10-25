from __future__ import annotations
import csv, datetime as dt, json, math
from pathlib import Path

EARTH_RADIUS_M = 6371008.8


class DataError(ValueError):
    pass


def haversine(a, b):
    lon1, lat1, lon2, lat2 = map(math.radians, (*a, *b))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(min(1, math.sqrt(h)))


def on_segment(p, a, b):
    cross = (p[0] - a[0]) * (b[1] - a[1]) - (p[1] - a[1]) * (b[0] - a[0])
    return (
        abs(cross) < 1e-12
        and min(a[0], b[0]) - 1e-12 <= p[0] <= max(a[0], b[0]) + 1e-12
        and min(a[1], b[1]) - 1e-12 <= p[1] <= max(a[1], b[1]) + 1e-12
    )


def ring_contains(point, ring):
    inside = False
    x, y = point
    for a, b in zip(ring, ring[1:]):
        if on_segment(point, a, b):
            return True
        if (a[1] > y) != (b[1] > y) and x < (b[0] - a[0]) * (y - a[1]) / (
            b[1] - a[1]
        ) + a[0]:
            inside = not inside
    return inside


def polygon_covers(point, rings):
    # Polygon boundaries, including hole boundaries, are covered (PostGIS ST_Covers).
    if any(on_segment(point, a, b) for ring in rings for a, b in zip(ring, ring[1:])):
        return True
    return ring_contains(point, rings[0]) and not any(
        ring_contains(point, r) for r in rings[1:]
    )


def coordinate(value):
    if (
        not isinstance(value, list)
        or len(value) != 2
        or any(
            isinstance(v, bool)
            or not isinstance(v, (int, float))
            or not math.isfinite(v)
            for v in value
        )
    ):
        raise DataError("좌표는 유한한 경도·위도 두 값이어야 합니다.")
    if not (-180 <= value[0] <= 180 and -90 <= value[1] <= 90):
        raise DataError("WGS84 좌표 범위를 벗어났습니다.")


def validate_collection(data, geometry_type, required):
    if (
        not isinstance(data, dict)
        or data.get("type") != "FeatureCollection"
        or not isinstance(data.get("features"), list)
    ):
        raise DataError("GeoJSON FeatureCollection이 필요합니다.")
    if not data["features"]:
        raise DataError("빈 레이어입니다.")
    seen = set()
    for f in data["features"]:
        if not isinstance(f, dict) or f.get("type") != "Feature":
            raise DataError("올바르지 않은 Feature입니다.")
        p = f.get("properties")
        if not isinstance(p, dict) or any(
            not isinstance(p.get(k), str) or not p[k].strip() for k in required
        ):
            raise DataError("필수 속성이 없거나 비어 있습니다: " + ", ".join(required))
        if p["id"] in seen:
            raise DataError("중복 ID: " + p["id"])
        seen.add(p["id"])
        g = f.get("geometry")
        if not isinstance(g, dict):
            raise DataError("geometry는 GeoJSON 객체여야 합니다.")
        if g.get("type") != geometry_type:
            raise DataError("지원하지 않는 geometry: " + str(g.get("type")))
        coords = g.get("coordinates")
        if geometry_type == "Point":
            coordinate(coords)
        else:
            if not isinstance(coords, list) or not coords:
                raise DataError("Polygon ring이 없습니다.")
            for ring in coords:
                if not isinstance(ring, list) or len(ring) < 4 or ring[0] != ring[-1]:
                    raise DataError("Polygon ring은 닫혀 있어야 합니다.")
                for c in ring:
                    coordinate(c)
                area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(ring, ring[1:]))
                if abs(area) < 1e-12:
                    raise DataError("면적이 0인 Polygon입니다.")
                # Reject crossing, nonadjacent edges instead of silently analyzing invalid rings.
                edges = list(zip(ring, ring[1:]))

                def orient(a, b, c):
                    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

                for i, (a, b) in enumerate(edges):
                    for j, (c, d) in enumerate(edges):
                        if j <= i + 1 or i == 0 and j == len(edges) - 1:
                            continue
                        if (
                            orient(a, b, c) * orient(a, b, d) < 0
                            and orient(c, d, a) * orient(c, d, b) < 0
                        ):
                            raise DataError("자기 교차 Polygon입니다.")
    return data["features"]


def load_dataset(directory):
    directory = Path(directory)
    specs = {
        "assets": ("Point", ["id", "name", "kind", "condition", "last_inspected"]),
        "centers": ("Point", ["id", "name"]),
        "zones": ("Polygon", ["id", "name"]),
        "hazards": ("Polygon", ["id", "name"]),
    }
    result = {}
    for name, (kind, required) in specs.items():
        try:
            data = json.loads(
                (directory / (name + ".geojson")).read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as e:
            raise DataError(f"{name} 입력을 읽을 수 없습니다: {e}") from e
        result[name] = validate_collection(data, kind, required)
    for f in result["assets"]:
        p = f["properties"]
        if p["condition"] not in ("OK", "REPAIR"):
            raise DataError("condition은 OK 또는 REPAIR여야 합니다.")
        try:
            dt.date.fromisoformat(p["last_inspected"])
        except ValueError as e:
            raise DataError("잘못된 점검 일자") from e
    return result


def analyze(dataset, as_of=dt.date(2026, 10, 25), radius=750.0):
    if not math.isfinite(radius) or not 0 < radius <= 10000:
        raise DataError("반경은 0 초과 10000m 이하입니다.")
    if not dataset["centers"]:
        raise DataError("지원 거점이 없습니다.")
    rows = []
    for feature in sorted(dataset["assets"], key=lambda f: f["properties"]["id"]):
        p = feature["properties"]
        point = feature["geometry"]["coordinates"]
        inspected = dt.date.fromisoformat(p["last_inspected"])
        if inspected > as_of:
            raise DataError("기준일보다 이후인 점검 일자가 있습니다: " + p["id"])
        nearest = min(
            dataset["centers"],
            key=lambda c: (
                haversine(point, c["geometry"]["coordinates"]),
                c["properties"]["id"],
            ),
        )
        distance = haversine(point, nearest["geometry"]["coordinates"])
        zone = next(
            (
                z["properties"]["name"]
                for z in sorted(dataset["zones"], key=lambda z: z["properties"]["id"])
                if polygon_covers(point, z["geometry"]["coordinates"])
            ),
            "구역 외",
        )
        hazard = any(
            polygon_covers(point, z["geometry"]["coordinates"])
            for z in dataset["hazards"]
        )
        overdue = (as_of - inspected).days > 180
        covered = distance <= radius
        score = (
            (35 if p["condition"] == "REPAIR" else 0)
            + (25 if overdue else 0)
            + (25 if hazard else 0)
            + (15 if not covered else 0)
        )
        reasons = [
            label
            for yes, label in [
                (p["condition"] == "REPAIR", "보수 필요"),
                (overdue, "점검 180일 초과"),
                (hazard, "가상 위험구역"),
                (not covered, "지원 반경 밖"),
            ]
            if yes
        ]
        rows.append(
            dict(
                id=p["id"],
                name=p["name"],
                kind=p["kind"],
                condition=p["condition"],
                last_inspected=p["last_inspected"],
                zone=zone,
                nearest_center=nearest["properties"]["id"],
                distance_m=round(distance, 2),
                covered=covered,
                hazard=hazard,
                overdue=overdue,
                score=score,
                priority="P1" if score >= 60 else "P2" if score >= 30 else "P3",
                reasons=" · ".join(reasons) or "일반 점검",
                lon=point[0],
                lat=point[1],
            )
        )
    return {
        "as_of": as_of.isoformat(),
        "radius_m": radius,
        "distance_method": "WGS84 coordinates / spherical haversine R=6371008.8m; PostGIS geography uses spheroid",
        "synthetic": True,
        "total": len(rows),
        "uncovered": sum(not r["covered"] for r in rows),
        "high_priority": sum(r["priority"] == "P1" for r in rows),
        "rows": rows,
    }


def csv_text(value):
    value = str(value)
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def write_csv(path, rows):
    fields = [
        "id",
        "name",
        "kind",
        "zone",
        "priority",
        "score",
        "nearest_center",
        "distance_m",
        "covered",
        "hazard",
        "overdue",
        "reasons",
        "last_inspected",
    ]
    with Path(path).open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(fields)
        writer.writerows([[csv_text(r[k]) for k in fields] for r in rows])
