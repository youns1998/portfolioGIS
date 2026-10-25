import json, subprocess
from pathlib import Path


def literal(v):
    return "'" + str(v).replace("'", "''") + "'"


def write_sql(path, dataset, report):
    sql = [
        "\\set ON_ERROR_STOP on",
        "BEGIN;",
        "SET LOCAL standard_conforming_strings = on;",
        "CREATE EXTENSION IF NOT EXISTS postgis;",
        "CREATE SCHEMA IF NOT EXISTS portfolio;",
    ]
    for name, features in dataset.items():
        geom = "Point" if name in ("assets", "centers") else "Polygon"
        sql.append(
            f"CREATE TABLE IF NOT EXISTS portfolio.{name}(id TEXT PRIMARY KEY, properties JSONB NOT NULL, geom geometry({geom},4326) NOT NULL);"
        )
        # Each import is a complete snapshot in this demonstration-only schema.
        sql.append(f"DELETE FROM portfolio.{name};")
        for f in features:
            p = literal(json.dumps(f["properties"], ensure_ascii=False))
            g = literal(json.dumps(f["geometry"]))
            sql.append(
                f"INSERT INTO portfolio.{name}(id,properties,geom) VALUES({literal(f['properties']['id'])},{p}::jsonb,ST_SetSRID(ST_GeomFromGeoJSON({g}),4326)) ON CONFLICT(id) DO UPDATE SET properties=EXCLUDED.properties,geom=EXCLUDED.geom;"
            )
        sql.append(
            f"CREATE INDEX IF NOT EXISTS {name}_geom_idx ON portfolio.{name} USING gist(geom);"
        )
    radius = report["radius_m"]
    date = literal(report["as_of"])
    sql.append(f"""CREATE OR REPLACE VIEW portfolio.analysis AS
WITH measured AS (
 SELECT a.id,a.properties->>'name' AS name,a.properties->>'condition' AS condition,
 c.id AS nearest_center,ST_Distance(a.geom::geography,c.geom::geography) AS distance_m,
 ST_DWithin(a.geom::geography,c.geom::geography,{radius}) AS covered,
 EXISTS(SELECT 1 FROM portfolio.hazards h WHERE ST_Covers(h.geom,a.geom)) AS hazard,
 ({date}::date-(a.properties->>'last_inspected')::date)>180 AS overdue
 FROM portfolio.assets a CROSS JOIN LATERAL (
 SELECT * FROM portfolio.centers c ORDER BY ST_Distance(a.geom::geography,c.geom::geography),c.id LIMIT 1) c
), scored AS (SELECT *,CASE WHEN condition='REPAIR' THEN 35 ELSE 0 END+CASE WHEN overdue THEN 25 ELSE 0 END+CASE WHEN hazard THEN 25 ELSE 0 END+CASE WHEN NOT covered THEN 15 ELSE 0 END AS score FROM measured)
SELECT *,CASE WHEN score>=60 THEN 'P1' WHEN score>=30 THEN 'P2' ELSE 'P3' END AS priority FROM scored;
COMMIT;
SELECT priority,count(*) FROM portfolio.analysis GROUP BY priority ORDER BY priority;""")
    Path(path).write_text("\n".join(sql) + "\n", encoding="utf-8")


def database_check(sql_file, report, psql="psql"):
    import csv, io

    subprocess.run(
        [psql, "-X", "-v", "ON_ERROR_STOP=1", "-f", str(sql_file)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    query = "COPY (SELECT id,nearest_center,distance_m,covered,hazard,overdue,score,priority FROM portfolio.analysis ORDER BY id) TO STDOUT WITH CSV HEADER"
    result = subprocess.run(
        [psql, "-X", "-v", "ON_ERROR_STOP=1", "-c", query],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    rows = list(csv.DictReader(io.StringIO(result.stdout)))
    if len(rows) != report["total"]:
        raise ValueError("PostGIS row count differs from Python output.")
    maximum = 0.0
    for actual, expected in zip(rows, report["rows"]):
        for key in ("id", "nearest_center", "priority"):
            if actual[key] != expected[key]:
                raise ValueError(f"PostGIS {key} mismatch: {actual}")
        for key in ("covered", "hazard", "overdue"):
            if (actual[key] == "t") != expected[key]:
                raise ValueError(f"PostGIS {key} mismatch: {actual}")
        if int(actual["score"]) != expected["score"]:
            raise ValueError("PostGIS score mismatch")
        maximum = max(
            maximum, abs(float(actual["distance_m"]) - expected["distance_m"])
        )
    if maximum > 5:
        raise ValueError(
            "Spherical/spheroidal distance difference exceeds the 5m fixture tolerance."
        )
    return {
        "rows_verified": len(rows),
        "max_distance_difference_m": round(maximum, 4),
        "method": "PostGIS geography spheroid compared with Python spherical haversine; fixture tolerance 5m",
    }
