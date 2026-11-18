import csv
from datetime import date
from io import StringIO
from pathlib import Path
import sqlite3
import tempfile
import unittest
from zipfile import ZipFile

from audit import COLUMNS, STANDARD, audit, sample, sha256


def archive(path, patches, year=2024):
    base = {
        "State Code": "01", "County Code": "001", "Site Num": "0001",
        "POC": "1", "Parameter Code": "88101",
        "Sample Duration": "24-HR BLK AVG", "Pollutant Standard": STANDARD,
        "Date Local": f"{year}-02-29", "Units of Measure": "Micrograms/cubic meter (LC)",
        "Event Type": "Included", "Observation Count": "24", "Arithmetic Mean": "20",
        "Method Code": "002", "State Name": "Alabama", "County Name": "Example County",
    }
    data = StringIO()
    writer = csv.DictWriter(data, fieldnames=sorted(COLUMNS))
    writer.writeheader()
    writer.writerows(base | patch for patch in patches)
    with ZipFile(path, "w") as target:
        target.writestr(f"daily_88101_{year}.csv", data.getvalue())


class AuditTests(unittest.TestCase):
    def test_event_pairs_coverage_and_equal_site_weights(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "source.zip"
            output = Path(folder) / "report"
            archive(path, [
                {}, {},  # Exact duplicate.
                {"Event Type": "Excluded", "Arithmetic Mean": "12"},
                {"POC": "2", "Arithmetic Mean": "40", "Event Type": "None"},
                {"Site Num": "0002", "Arithmetic Mean": "50"},
                {"Site Num": "0002", "Method Code": "003", "Event Type": "Excluded",
                 "Arithmetic Mean": "45"},  # Never pair two methods.
                {"County Code": "003", "Sample Duration": "1 HOUR", "Pollutant Standard": ""},
                {"County Code": "004", "Arithmetic Mean": "nan"},
            ])
            quality = audit(path, 2024, output, sha256(path))
            self.assertEqual(quality["days"], 366)
            self.assertEqual(quality["counts"]["invalid_sample"], 1)
            self.assertEqual(quality["counts"]["monitor_days"], 3)
            self.assertEqual(quality["regions"], 3)
            self.assertEqual(quality["regions_with_daily_coverage"], 1)
            self.assertEqual(quality["matched_event_pairs"], 1)
            self.assertEqual(quality["weighted_mean_absolute_event_delta"], 8)
            with (output / "county_coverage.csv").open(newline="", encoding="utf-8") as stream:
                counties = list(csv.DictReader(stream))
            self.assertEqual(counties[0]["aqs_region"], "01001")
            self.assertEqual(counties[0]["mean_observed_ug_m3"], "40.0")
            self.assertEqual(counties[1]["observed_days"], "0")
            self.assertEqual(counties[1]["mean_observed_ug_m3"], "")
            with (output / "monthly_coverage.csv").open(newline="", encoding="utf-8") as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 36)
            audit(path, 2024, output)
            db = sqlite3.connect(output / "audit.sqlite")
            try:
                self.assertEqual(db.execute("SELECT count(*) FROM samples").fetchone()[0], 6)
            finally:
                db.close()

    def test_duration_preference_and_conflict(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "source.zip"
            output = Path(folder) / "report"
            archive(path, [
                {},
                {"Sample Duration": "24 HOUR", "Arithmetic Mean": "15"},
                {"Site Num": "0002"},
                {"Site Num": "0002", "Arithmetic Mean": "21"},
            ])
            audit(path, 2024, output)
            db = sqlite3.connect(output / "audit.sqlite")
            try:
                self.assertEqual(
                    db.execute("SELECT site, duration, value FROM monitor_days").fetchall(),
                    [("0001", "24 HOUR", 15.0)],
                )
            finally:
                db.close()

    def test_bad_hash_does_not_create_outputs(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "source.zip"
            path.write_bytes(b"fixture")
            output = Path(folder) / "report"
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                audit(path, 2024, output, "wrong")
            self.assertFalse(output.exists())

    def test_unsupported_unit_is_rejected(self):
        record = {
            "Site Num": "0001", "POC": "1", "Event Type": "None",
            "Arithmetic Mean": "5", "Units of Measure": "ppm", "Method Code": "001",
        }
        with self.assertRaisesRegex(ValueError, "Unexpected reported units"):
            sample(record, "01001", date(2024, 1, 1))


if __name__ == "__main__":
    unittest.main()
