# Career summary

**FR**

- Développement d’un audit reproductible de couverture PM2.5 sur 847 162 lignes EPA AirData, avec ingestion ZIP en flux et agrégats SQLite contrôlés.
- Mesure des lacunes calendaires pour 636 régions et comparaison de 139 résumés appariés autour d’événements exceptionnels.

**EN**

- Built a reproducible PM2.5 coverage audit over 847,162 EPA AirData rows using streamed ZIP ingestion and validated SQLite aggregates.
- Measured calendar gaps across 636 regions and compared 139 matched instrument-day summaries around exceptional events.

## Demonstrated skills

Python ETL, SQL window functions, provenance, measurement quality, analytical aggregation, and reproducible runtime and test reporting.

## Interview questions

- How can instruments at the same site bias an average?
- Why exclude short-duration and alternative aggregate rows?
- Why does sparse calendar coverage fail to establish exposure or regulatory completeness?
- Why does the paired event comparison say little about monitors with missing counterpart summaries?

## Two-minute explanation

EPA publishes daily rows alongside alternate durations and event variants. A monitor is identified by site and POC. The pipeline selects comparable 24-hour summaries, collapses equal duplicates within a method, and makes conflicts and alternative variants explicit. It aggregates instruments to sites, sites to county-days, then calendar coverage to counties. In 2023, 87 of 636 reported AQS regions had fewer than half their calendar days covered.

## Five-minute explanation

Show the fixed source archive and SHA-256. Walk through the SQL CTEs and compare the three levels of weighting. Explain the difference between observed calendar-day coverage and completeness of a scheduled monitoring network. Show the grouped event-pair CSV, explain why it uses only the same instrument/day/duration/method comparisons, and describe the fixture that rejects cross-method matches. Present county coverage stratified by month and describe potential bias from site placement, method configuration and missing days.

## Follow-up experiments

Join EPA schedule and monitoring objectives, distinguish elective sampling from missing eligible observations, and compare geographic coverage across years.
