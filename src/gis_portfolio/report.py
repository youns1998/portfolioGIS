import html, json
from pathlib import Path

ASSETS = Path(__file__).resolve().parent


def write_html(path, dataset, report):
    points = [
        f["geometry"]["coordinates"] for f in dataset["assets"] + dataset["centers"]
    ]
    xs, ys = zip(*points)
    xmin, xmax = min(xs) - 0.003, max(xs) + 0.003
    ymin, ymax = min(ys) - 0.003, max(ys) + 0.003

    def xy(p):
        return (
            (p[0] - xmin) / (xmax - xmin) * 960 + 20,
            640 - (p[1] - ymin) / (ymax - ymin) * 600,
        )

    polygons = []
    for name, color in [("zones", "#f0f3f6"), ("hazards", "#fff1e5")]:
        for feature in dataset[name]:
            # Even-odd fill preserves Polygon holes in the visual result too.
            shape = " ".join(
                "M " + " L ".join(f"{x:.2f},{y:.2f}" for x, y in map(xy, ring)) + " Z"
                for ring in feature["geometry"]["coordinates"]
            )
            polygons.append(
                '<path d="'
                + shape
                + f'" fill-rule="evenodd" fill="{color}" stroke="#d1d9e0"><title>'
                + html.escape(feature["properties"]["name"])
                + "</title></path>"
            )
    markers = []
    for row in report["rows"]:
        x, y = xy((row["lon"], row["lat"]))
        markers.append(
            f'<circle class="asset" tabindex="0" role="button" aria-label="{html.escape(row["name"], quote=True)}" data-id="{html.escape(row["id"], quote=True)}" data-priority="{row["priority"]}" cx="{x:.2f}" cy="{y:.2f}" r="7"><title>'
            + html.escape(row["name"])
            + "</title></circle>"
        )
    for feature in dataset["centers"]:
        x, y = xy(feature["geometry"]["coordinates"])
        markers.append(
            f'<rect x="{x - 6:.2f}" y="{y - 6:.2f}" width="12" height="12" fill="#59636e" stroke="white"><title>'
            + html.escape(feature["properties"]["name"])
            + "</title></rect>"
        )
    data = json.dumps(report, ensure_ascii=False).replace("<", "\\u003c")
    source = (
        (ASSETS / "templates/report.html")
        .read_text(encoding="utf-8")
        .replace(
            "@@STYLES@@", (ASSETS / "static/report.css").read_text(encoding="utf-8")
        )
        .replace(
            "@@SCRIPT@@", (ASSETS / "static/report.js").read_text(encoding="utf-8")
        )
        .replace("@@POLYGONS@@", "".join(polygons))
        .replace("@@MARKERS@@", "".join(markers))
        .replace("@@DATA@@", data)
    )
    Path(path).write_text(source, encoding="utf-8")
