import argparse, datetime, json, sys, subprocess
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from functools import partial
from .analysis import load_dataset, analyze, write_csv, DataError
from .geopackage import write_geopackage, write_qgis
from .postgis import write_sql, database_check
from .report import write_html


def main(argv=None):
    parser = argparse.ArgumentParser(description="가상 공공시설 점검 우선순위 분석")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("analyze")
    run.add_argument("--input", default="data")
    run.add_argument("--output", default="output")
    run.add_argument("--as-of", default="2026-10-25")
    run.add_argument("--radius", type=float, default=750)
    serve = sub.add_parser("serve")
    serve.add_argument("--output", default="output")
    serve.add_argument("--port", type=int, default=8787)
    db = sub.add_parser("database-check")
    db.add_argument("--output", default="output")
    db.add_argument("--psql", default="psql")
    args = parser.parse_args(argv)
    try:
        out = Path(args.output).resolve()
        if args.command == "analyze":
            source = Path(args.input).resolve()
            if source == out or source.is_relative_to(out):
                raise DataError(
                    "입력 폴더 또는 그 상위 폴더를 출력으로 지정할 수 없습니다."
                )
            dataset = load_dataset(source)
            report = analyze(
                dataset, datetime.date.fromisoformat(args.as_of), args.radius
            )
            out.mkdir(parents=True, exist_ok=True)
            # A new analysis must never retain evidence from a previous database run.
            (out / "database-check.json").unlink(missing_ok=True)
            (out / "report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            write_csv(out / "facilities.csv", report["rows"])
            write_geopackage(out / "analysis.gpkg", dataset, report)
            write_qgis(out / "facility-review.qgs")
            write_sql(out / "postgis.sql", dataset, report)
            write_html(out / "index.html", dataset, report)
            enriched = {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [r["lon"], r["lat"]],
                        },
                        "properties": r,
                    }
                    for r in report["rows"]
                ],
            }
            (out / "facilities.geojson").write_text(
                json.dumps(enriched, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(
                json.dumps(
                    {k: v for k, v in report.items() if k != "rows"}, ensure_ascii=False
                )
            )
        elif args.command == "serve":
            if not (out / "index.html").exists():
                raise DataError("먼저 analyze를 실행하세요.")
            server = ThreadingHTTPServer(
                ("127.0.0.1", args.port),
                partial(SimpleHTTPRequestHandler, directory=str(out)),
            )
            print(f"Local: http://127.0.0.1:{args.port}", flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
        else:
            report = json.loads((out / "report.json").read_text(encoding="utf-8"))
            result = database_check(out / "postgis.sql", report, args.psql)
            (out / "database-check.json").write_text(
                json.dumps(result, indent=2) + "\n", encoding="utf-8"
            )
            print(json.dumps(result))
        return 0
    except subprocess.CalledProcessError as error:
        print(
            "PostGIS 실행 오류: " + (error.stderr or str(error)).strip(),
            file=sys.stderr,
        )
        return 2
    except (DataError, ValueError, OSError) as error:
        print("입력/실행 오류: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
