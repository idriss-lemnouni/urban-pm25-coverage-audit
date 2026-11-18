-- Collapse duplicate rows before choosing one duration per monitoring instrument.
CREATE TABLE monitor_days AS
WITH variants AS (
    SELECT region, site, poc, day, duration, method, event,
           CASE WHEN min(value) = max(value) THEN min(value) END AS value,
           min(value) <> max(value) AS conflict
    FROM samples
    GROUP BY region, site, poc, day, duration, method, event
), by_method AS (
    SELECT region, site, poc, day, duration, method,
           max(CASE WHEN event IN ('none', 'included') THEN value END) AS baseline,
           max(CASE WHEN event = 'included' THEN value END) AS included,
           max(CASE WHEN event = 'excluded' THEN value END) AS excluded
    FROM variants
    WHERE event <> 'concurred_excluded'
    GROUP BY region, site, poc, day, duration, method
    HAVING sum(conflict) = 0
       AND count(DISTINCT CASE WHEN event IN ('none', 'included') THEN value END) = 1
), unambiguous AS (
    SELECT region, site, poc, day, duration, min(baseline) AS value,
           CASE WHEN count(*) = 1 THEN max(excluded - included) END AS exclusion_delta
    FROM by_method
    GROUP BY region, site, poc, day, duration
    HAVING min(baseline) = max(baseline)
), ranked AS (
    SELECT *,
           row_number() OVER (
               PARTITION BY region, site, poc, day
               ORDER BY CASE duration WHEN '24 HOUR' THEN 0 ELSE 1 END
           ) AS priority
    FROM unambiguous
)
SELECT region, site, poc, day, duration, value, exclusion_delta
FROM ranked WHERE priority = 1;

CREATE UNIQUE INDEX monitor_day_key ON monitor_days (region, site, poc, day);

CREATE TABLE site_days AS
SELECT region, site, day, avg(value) AS site_mean, count(*) AS instruments
FROM monitor_days GROUP BY region, site, day;

CREATE TABLE county_days AS
SELECT region, day, avg(site_mean) AS county_site_mean, count(*) AS sites
FROM site_days GROUP BY region, day;
