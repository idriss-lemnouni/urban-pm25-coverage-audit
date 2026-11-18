"""Stream AQS daily archives into an auditable county reporting database."""
from __future__ import annotations

import argparse
import calendar
from collections import Counter
import csv
from datetime import date
import hashlib
from io import TextIOWrapper
import json
import logging
import math
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import time
from urllib.request import urlopen
from zipfile import BadZipFile, ZipFile

from report import write_reports

EPA_BASE = "https://aqs.epa.gov/aqsweb/airdata"
STANDARD = "PM25 24-hour 2012"
DURATIONS = {"24 HOUR", "24-HR BLK AVG"}
EVENTS = {
    "none": "none", "no events": "none",
    "included": "included", "events included": "included",
    "excluded": "excluded", "events excluded": "excluded",
    "concurred events excluded": "concurred_excluded",
}
COLUMNS = {
    "State Code", "County Code", "Site Num", "POC", "Parameter Code",
    "Sample Duration", "Pollutant Standard", "Date Local", "Units of Measure",
    "Event Type", "Observation Count", "Arithmetic Mean", "Method Code",
    "State Name", "County Name",
}
SCHEMA = """
CREATE TABLE regions (region TEXT PRIMARY KEY, state TEXT, county TEXT);
CREATE TABLE samples (
    region TEXT REFERENCES regions DEFERRABLE INITIALLY DEFERRED,
    site TEXT, poc INTEGER, day TEXT,
    duration TEXT, method TEXT, event TEXT, value REAL NOT NULL
);
"""
BATCH_SIZE = 5000


def epa_url(year: int) -> str:
    return f"{EPA_BASE}/daily_88101_{year}.zip"


def sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def fetch(year: int, path: Path, expected_hash: str | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=path.parent) as folder:
        staged = Path(folder) / path.name
        with urlopen(epa_url(year), timeout=45) as source, staged.open("wb") as target:
            size = 0
            while chunk := source.read(1024 * 1024):
                size += len(chunk)
                if size > 60_000_000:
                    raise ValueError("Download exceeded the 60 MB compressed archive limit")
                target.write(chunk)
        with ZipFile(staged) as archive:
            archive.getinfo(f"daily_88101_{year}.csv")
        digest = sha256(staged)
        if expected_hash and digest != expected_hash:
            raise ValueError(f"SHA-256 mismatch: {digest}")
        staged.replace(path)
    print(f"{digest}  {path}")


def region_code(row: dict[str, str]) -> str:
    state, county = row["State Code"], row["County Code"]
    if not (len(state) == 2 and state.isascii() and state.isdecimal()
            and len(county) == 3 and county.isascii() and county.isdecimal()):
        raise ValueError("Invalid AQS region code")
    return state + county


def sample(row: dict[str, str], region: str, day: date) -> tuple:
    site = row["Site Num"]
    event = EVENTS.get(row["Event Type"].strip().lower())
    value = float(row["Arithmetic Mean"])
    method = row["Method Code"].strip()
    poc = int(row["POC"])
    if row["Units of Measure"] != "Micrograms/cubic meter (LC)":
        raise ValueError("Unexpected reported units")
    if (len(site) != 4 or not site.isascii() or not site.isdecimal()
            or not event or not method or poc < 1
            or int(row["Observation Count"]) <= 0 or not math.isfinite(value)):
        raise ValueError("Invalid monitor-day fields")
    return region, site, poc, day.isoformat(), row["Sample Duration"], method, event, value


def ingest(db: sqlite3.Connection, path: Path, year: int) -> Counter:
    quality = Counter()
    regions = {}
    batch = []
    insert = "INSERT INTO samples VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
    with ZipFile(path) as archive:
        item = archive.getinfo(f"daily_88101_{year}.csv")
        if item.file_size > 1_000_000_000:
            raise ValueError("CSV member exceeds the 1 GB uncompressed limit")
        with archive.open(item) as raw, TextIOWrapper(raw, encoding="utf-8-sig") as stream:
            records = csv.DictReader(stream)
            if missing := COLUMNS.difference(records.fieldnames or []):
                raise ValueError(f"Missing AQS columns: {', '.join(sorted(missing))}")
            for row in records:
                quality["source_rows"] += 1
                if row["Parameter Code"] != "88101":
                    quality["other_parameter"] += 1
                    continue
                try:
                    code = region_code(row)
                    day = date.fromisoformat(row["Date Local"])
                except (ValueError, TypeError):
                    quality["invalid_identity_or_date"] += 1
                    continue
                if day.year != year:
                    quality["outside_year"] += 1
                    continue
                regions.setdefault(code, (row["State Name"], row["County Name"]))
                if row["Pollutant Standard"] != STANDARD or row["Sample Duration"] not in DURATIONS:
                    quality["out_of_scope_aggregation"] += 1
                    continue
                try:
                    batch.append(sample(row, code, day))
                except (ValueError, TypeError, AttributeError):
                    quality["invalid_sample"] += 1
                    continue
                quality["staged_rows"] += 1
                if len(batch) >= BATCH_SIZE:
                    db.executemany(insert, batch)
                    batch.clear()
            db.executemany(insert, batch)
    db.executemany("INSERT INTO regions VALUES (?, ?, ?)", (
        (code, *labels) for code, labels in sorted(regions.items())
    ))
    return quality


def audit(path: Path, year: int, output: Path, expected_hash: str | None = None) -> dict:
    start = time.perf_counter()
    checksum = sha256(path)
    if expected_hash and checksum != expected_hash:
        raise ValueError(f"SHA-256 mismatch: {checksum}")
    output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output) as folder:
        stage = Path(folder)
        database = stage / "audit.sqlite"
        db = sqlite3.connect(database)
        try:
            db.execute("PRAGMA foreign_keys = ON")
            db.executescript(SCHEMA)
            with db:
                counts = ingest(db, path, year)
            logging.info("Read %s source rows and staged %s", counts["source_rows"], counts["staged_rows"])
            if not counts["staged_rows"]:
                raise ValueError("No rows match the selected standard and daily durations")
            db.executescript(Path(__file__).with_name("audit.sql").read_text(encoding="utf-8"))
            for table in ("monitor_days", "site_days", "county_days"):
                counts[table] = db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            quality = {
                "year": year,
                "days": 365 + calendar.isleap(year),
                "source_url": epa_url(year),
                "local_archive_bytes": path.stat().st_size,
                "sha256": checksum,
                "standard": STANDARD,
                "counts": dict(sorted(counts.items())),
            }
            write_reports(db, stage, quality)
            quality["runtime_seconds"] = round(time.perf_counter() - start, 3)
            (stage / "quality.json").write_text(json.dumps(quality, indent=2) + "\n", encoding="utf-8")
        finally:
            db.close()
        for staged in sorted(stage.iterdir()):
            staged.replace(output / staged.name)
    return quality


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("fetch", "audit"):
        command = commands.add_parser(name)
        command.add_argument("--year", required=True, type=int, choices=range(1999, 2100), metavar="YYYY")
        command.add_argument("--archive", required=True, type=Path)
        command.add_argument("--sha256")
    commands.choices["audit"].add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        if args.command == "fetch":
            fetch(args.year, args.archive, args.sha256)
        else:
            result = audit(args.archive, args.year, args.out, args.sha256)
            print(json.dumps(result))
    except (OSError, ValueError, KeyError, sqlite3.Error, BadZipFile) as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    main()
