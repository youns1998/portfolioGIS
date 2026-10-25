import json, sqlite3, struct
from pathlib import Path

WKT = 'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433],AUTHORITY["EPSG","4326"]]'


def geometry_blob(geometry):
    coords = geometry["coordinates"]
    if geometry["type"] == "Point":
        wkb = struct.pack("<BIdd", 1, 1, *coords)
    else:
        wkb = struct.pack("<BII", 1, 3, len(coords))
        for ring in coords:
            wkb += struct.pack("<I", len(ring)) + b"".join(
                struct.pack("<dd", *p) for p in ring
            )
    return b"GP" + bytes([0, 1]) + struct.pack("<i", 4326) + wkb


def write_geopackage(path, dataset, report):
    path = Path(path)
    temp = path.with_suffix(".tmp.gpkg")
    if temp.exists():
        temp.unlink()
    conn = sqlite3.connect(temp)
    try:
        conn.executescript("""PRAGMA application_id=1196444487; PRAGMA user_version=10300;
CREATE TABLE gpkg_spatial_ref_sys(srs_name TEXT NOT NULL,srs_id INTEGER NOT NULL PRIMARY KEY,organization TEXT NOT NULL,organization_coordsys_id INTEGER NOT NULL,definition TEXT NOT NULL,description TEXT);
CREATE TABLE gpkg_contents(table_name TEXT PRIMARY KEY,data_type TEXT NOT NULL,identifier TEXT UNIQUE,description TEXT DEFAULT '',last_change DATETIME NOT NULL,min_x DOUBLE,min_y DOUBLE,max_x DOUBLE,max_y DOUBLE,srs_id INTEGER);
CREATE TABLE gpkg_geometry_columns(table_name TEXT NOT NULL,column_name TEXT NOT NULL,geometry_type_name TEXT NOT NULL,srs_id INTEGER NOT NULL,z TINYINT NOT NULL,m TINYINT NOT NULL,PRIMARY KEY(table_name,column_name));""")
        conn.executemany(
            "INSERT INTO gpkg_spatial_ref_sys VALUES(?,?,?,?,?,?)",
            [
                ("Undefined Cartesian", -1, "NONE", -1, "undefined", ""),
                ("Undefined geographic", 0, "NONE", 0, "undefined", ""),
                ("WGS 84", 4326, "EPSG", 4326, WKT, "Longitude, latitude"),
            ],
        )
        by_id = {r["id"]: r for r in report["rows"]}
        for name, features in dataset.items():
            conn.execute(
                f'CREATE TABLE "{name}"(fid INTEGER PRIMARY KEY AUTOINCREMENT,geom BLOB NOT NULL,asset_id TEXT UNIQUE,name TEXT,priority TEXT,score INTEGER,properties TEXT)'
            )
            for f in features:
                props = (
                    {**f["properties"], **by_id.get(f["properties"]["id"], {})}
                    if name == "assets"
                    else f["properties"]
                )
                conn.execute(
                    f'INSERT INTO "{name}"(geom,asset_id,name,priority,score,properties) VALUES(?,?,?,?,?,?)',
                    (
                        geometry_blob(f["geometry"]),
                        props["id"],
                        props["name"],
                        props.get("priority"),
                        props.get("score"),
                        json.dumps(props, ensure_ascii=False),
                    ),
                )
            points = (
                [f["geometry"]["coordinates"] for f in features]
                if features[0]["geometry"]["type"] == "Point"
                else [
                    p
                    for f in features
                    for ring in f["geometry"]["coordinates"]
                    for p in ring
                ]
            )
            xs, ys = zip(*points)
            conn.execute(
                "INSERT INTO gpkg_contents VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    name,
                    "features",
                    name,
                    "Synthetic portfolio data",
                    report["as_of"] + "T00:00:00.000Z",
                    min(xs),
                    min(ys),
                    max(xs),
                    max(ys),
                    4326,
                ),
            )
            conn.execute(
                "INSERT INTO gpkg_geometry_columns VALUES(?,?,?,?,?,?)",
                (name, "geom", features[0]["geometry"]["type"].upper(), 4326, 0, 0),
            )
        conn.commit()
    finally:
        conn.close()
    temp.replace(path)


def write_qgis(path):
    from xml.etree.ElementTree import Element, SubElement, ElementTree

    q = Element(
        "qgis", version="3.34.0", projectname="Public facility priority / synthetic"
    )
    tree = SubElement(q, "layer-tree-group", name="Layers")
    layers = SubElement(q, "projectlayers")
    for name in ("assets", "centers", "hazards", "zones"):
        SubElement(tree, "layer-tree-layer", id=name, name=name, checked="Qt::Checked")
        layer = SubElement(
            layers,
            "maplayer",
            type="vector",
            geometry="Point" if name in ("assets", "centers") else "Polygon",
            autoRefreshEnabled="0",
        )
        for tag, value in [
            ("id", name),
            ("layername", name),
            ("datasource", "./analysis.gpkg|layername=" + name),
            ("provider", "ogr"),
        ]:
            SubElement(layer, tag).text = value
        s = SubElement(SubElement(layer, "srs"), "spatialrefsys")
        SubElement(s, "authid").text = "EPSG:4326"
        SubElement(s, "wkt").text = WKT
        if name == "assets":
            renderer = SubElement(
                layer,
                "renderer-v2",
                type="categorizedSymbol",
                attr="priority",
                symbollevels="0",
            )
            cats = SubElement(renderer, "categories")
            symbols = SubElement(renderer, "symbols")
            for n, (priority, color) in enumerate(
                [
                    ("P1", "185,62,50,255"),
                    ("P2", "203,146,52,255"),
                    ("P3", "73,126,102,255"),
                ]
            ):
                SubElement(
                    cats,
                    "category",
                    value=priority,
                    label=priority,
                    symbol=str(n),
                    render="true",
                )
                symbol = SubElement(
                    symbols, "symbol", name=str(n), type="marker", alpha="1"
                )
                sl = SubElement(
                    symbol,
                    "layer",
                    {"class": "SimpleMarker", "pass": "0", "enabled": "1"},
                )
                opt = SubElement(sl, "Option", type="Map")
                for key, value in [
                    ("name", "circle"),
                    ("color", color),
                    ("size", "3"),
                    ("outline_color", "255,255,255,255"),
                ]:
                    SubElement(opt, "Option", name=key, value=value, type="QString")
    SubElement(q, "title").text = "가상 공공시설 점검 우선순위"
    ElementTree(q).write(path, encoding="utf-8", xml_declaration=True)
