import copy, datetime, json, sqlite3, struct, subprocess, sys, tempfile, unittest
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gis_portfolio.analysis import (
    DataError,
    analyze,
    coordinate,
    csv_text,
    haversine,
    load_dataset,
    polygon_covers,
    validate_collection,
)
from gis_portfolio.geopackage import write_geopackage, write_qgis
from gis_portfolio.cli import main

ROOT = Path(__file__).resolve().parents[1]


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.data = load_dataset(ROOT / "data")

    def test_known_geodesic_distance(self):
        self.assertAlmostEqual(haversine((0, 0), (0, 1)), 111195.0802, places=3)

    def test_zero_and_symmetry(self):
        self.assertEqual(haversine((127, 36), (127, 36)), 0)
        self.assertAlmostEqual(
            haversine((127, 36), (128, 37)), haversine((128, 37), (127, 36))
        )

    def test_polygon_edge_and_hole(self):
        rings = [
            [[0, 0], [4, 0], [4, 4], [0, 4], [0, 0]],
            [[1, 1], [2, 1], [2, 2], [1, 2], [1, 1]],
        ]
        self.assertTrue(polygon_covers([0, 2], rings))
        self.assertFalse(polygon_covers([1.5, 1.5], rings))
        self.assertTrue(polygon_covers([1, 1.5], rings))
        self.assertFalse(polygon_covers([5, 5], rings))

    def test_duplicate_id_rejected(self):
        features = copy.deepcopy(self.data["assets"])
        features.append(features[0])
        self.assertRaises(
            DataError,
            validate_collection,
            {"type": "FeatureCollection", "features": features},
            "Point",
            ["id", "name"],
        )

    def test_non_finite_coordinate(self):
        self.assertRaises(DataError, coordinate, [float("nan"), 36])
        self.assertRaises(DataError, coordinate, [127, float("inf")])

    def test_boolean_coordinate_rejected(self):
        self.assertRaises(DataError, coordinate, [True, 36])

    def test_projected_coordinate_rejected(self):
        self.assertRaises(DataError, coordinate, [200000, 450000])

    def test_open_ring_rejected(self):
        feature = copy.deepcopy(self.data["zones"][0])
        feature["geometry"]["coordinates"][0].pop()
        self.assertRaises(
            DataError,
            validate_collection,
            {"type": "FeatureCollection", "features": [feature]},
            "Polygon",
            ["id", "name"],
        )

    def test_missing_field_rejected(self):
        feature = copy.deepcopy(self.data["assets"][0])
        del feature["properties"]["name"]
        self.assertRaises(
            DataError,
            validate_collection,
            {"type": "FeatureCollection", "features": [feature]},
            "Point",
            ["id", "name"],
        )

    def test_synthetic_result_is_deterministic(self):
        first = analyze(self.data)
        second = analyze(self.data)
        self.assertEqual(first, second)
        self.assertEqual(first["total"], 36)
        self.assertTrue(first["synthetic"])
        self.assertGreater(first["high_priority"], 0)
        self.assertGreater(first["uncovered"], 0)

    def test_score_factors(self):
        for row in analyze(self.data)["rows"]:
            expected = (
                (35 if row["condition"] == "REPAIR" else 0)
                + (25 if row["overdue"] else 0)
                + (25 if row["hazard"] else 0)
                + (15 if not row["covered"] else 0)
            )
            self.assertEqual(expected, row["score"])
            self.assertEqual(
                row["priority"],
                "P1" if expected >= 60 else "P2" if expected >= 30 else "P3",
            )

    def test_radius_boundaries(self):
        self.assertRaises(DataError, analyze, self.data, radius=0)
        self.assertRaises(DataError, analyze, self.data, radius=float("nan"))
        self.assertRaises(DataError, analyze, self.data, radius=10001)

    def test_larger_radius_never_reduces_coverage(self):
        self.assertLessEqual(
            analyze(self.data, radius=1000)["uncovered"],
            analyze(self.data, radius=100)["uncovered"],
        )

    def test_no_centers_rejected(self):
        self.data["centers"] = []
        self.assertRaises(DataError, analyze, self.data)

    def test_future_inspection_rejected(self):
        self.data["assets"][0]["properties"]["last_inspected"] = "2030-01-01"
        self.assertRaises(DataError, analyze, self.data)

    def test_csv_injection_and_escaping(self):
        self.assertEqual(csv_text("=1+2"), "'=1+2")
        self.assertEqual(csv_text(" +SUM(A1)"), "' +SUM(A1)")

    def test_geopackage_structure_and_geometry(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.gpkg"
            report = analyze(self.data)
            write_geopackage(path, self.data, report)
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(
                    db.execute("pragma integrity_check").fetchone()[0], "ok"
                )
                self.assertEqual(
                    db.execute("pragma application_id").fetchone()[0], 1196444487
                )
                self.assertEqual(
                    db.execute("select count(*) from assets").fetchone()[0], 36
                )
                self.assertEqual(
                    db.execute("select count(*) from gpkg_contents").fetchone()[0], 4
                )
                geom = db.execute(
                    "select geom from assets order by asset_id limit 1"
                ).fetchone()[0]
                self.assertEqual(geom[:2], b"GP")
                self.assertEqual(struct.unpack("<i", geom[4:8])[0], 4326)
                self.assertEqual(struct.unpack("<BI", geom[8:13]), (1, 1))

    def test_all_artifacts_and_no_network_dependency(self):
        with tempfile.TemporaryDirectory() as directory:
            stale = Path(directory) / "database-check.json"
            stale.write_text('{"rows_verified":999}', encoding="utf-8")
            self.assertEqual(
                main(["analyze", "--input", str(ROOT / "data"), "--output", directory]),
                0,
            )
            for name in [
                "report.json",
                "facilities.csv",
                "facilities.geojson",
                "analysis.gpkg",
                "facility-review.qgs",
                "postgis.sql",
                "index.html",
            ]:
                self.assertTrue((Path(directory) / name).is_file(), name)
            from xml.etree.ElementTree import parse

            project = parse(Path(directory) / "facility-review.qgs")
            self.assertEqual(len(project.findall(".//maplayer")), 4)
            self.assertFalse(
                stale.exists(), "reanalysis must invalidate prior database evidence"
            )
            html = (Path(directory) / "index.html").read_text(encoding="utf-8")
            self.assertNotIn('<script src="http', html)
            self.assertIn("가상", html)

    def test_malformed_geometry_rejected(self):
        feature = self.data["assets"][0]
        feature["geometry"] = [1, 2]
        self.assertRaises(
            DataError,
            validate_collection,
            {"type": "FeatureCollection", "features": [feature]},
            "Point",
            ["id", "name"],
        )

    def test_html_user_text_cannot_close_script(self):
        from gis_portfolio.report import write_html

        name = "</script><img src=x onerror=alert(1)>"
        self.data["assets"][0]["properties"]["name"] = name
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "index.html"
            write_html(output, self.data, analyze(self.data))
            html = output.read_text(encoding="utf-8")
            self.assertNotIn(name, html)
            self.assertIn("&lt;/script&gt;&lt;img", html)
            self.assertIn(r"\u003c/script>", html)

    def test_input_output_collision_rejected(self):
        self.assertEqual(
            main(
                [
                    "analyze",
                    "--input",
                    str(ROOT / "data"),
                    "--output",
                    str(ROOT / "data"),
                ]
            ),
            2,
        )


if __name__ == "__main__":
    unittest.main()
