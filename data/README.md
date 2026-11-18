# Data

EPA AirData, Air Quality System daily PM2.5 parameter 88101. The 2023 demonstration uses the EPA ZIP containing 847,162 summary rows. The downloaded ZIP was 9,919,616 bytes and the uncompressed member was 319,126,720 bytes. The pipeline reads the ZIP directly. [Archive](https://aqs.epa.gov/aqsweb/airdata/daily_88101_2023.zip) · [EPA data dictionary](https://aqs.epa.gov/aqsweb/airdata/FileFormats.html)

The finite daily arithmetic mean is expressed in µg/m³ at local conditions. AQS state/county codes identify a region, site and POC identify a sampling instrument, and Method Code identifies the reported method. The audit uses the monitor-local standard date. It selects the source export's `PM25 24-hour 2012` summaries for `24 HOUR` and `24-HR BLK AVG`. Short labels in the observed export and long labels in the EPA documentation are accepted for event status.

| Check | Handling |
| --- | --- |
| ZIP member, header, SHA-256 | Reject missing member, missing column or hash mismatch. |
| Parameter, standard, durations | Diagnose out-of-scope aggregate rows. |
| Local date and units | Identify year mismatch, malformed date or unexpected unit. |
| Duplicate observations and divergences | Collapse identical values by typed key; exclude conflicting variants for the applicable method. |
| Event exclusions | Compare only when both summaries are available for the selected instrument-day, duration and unambiguous method. |

The source data are in the U.S. public domain according to EPA. Local raw archives and database files are excluded from Git. [EPA AirData reuse terms](https://www.epa.gov/outdoor-air-quality-data/do-i-need-request-permission-use-monitoring-data-and-graphics-airdata)
