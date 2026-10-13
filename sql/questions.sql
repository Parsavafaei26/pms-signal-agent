-- Example PMS questions answered with SQL. Run: python3 scripts/run_questions.py

-- name: Complaints per failure mode and year, with share of all complaints
SELECT primary_fm, f.name,
       SUM(year = '2023') AS y2023, SUM(year = '2024') AS y2024, SUM(year = '2025') AS y2025,
       ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM complaints), 1) AS pct_all
FROM complaints JOIN failure_modes f ON f.code = primary_fm
GROUP BY primary_fm ORDER BY COUNT(*) DESC;

-- name: Hazards with no row in the reference FMEA, and how serious they were
SELECT f.code, f.name, COUNT(c.report_number) AS complaints,
       SUM(c.severity IN ('S3','S4','S5')) AS serious, SUM(c.retained_fragment) AS retained_fragments
FROM failure_modes f LEFT JOIN complaints c ON c.primary_fm = f.code
WHERE f.fmea_row IS NULL AND f.code <> 'FM12'
GROUP BY f.code ORDER BY complaints DESC;

-- name: Where retained fragments come from (failure mode x phase of use)
SELECT primary_fm, phase, COUNT(*) AS retained_fragments
FROM complaints WHERE retained_fragment = 1
GROUP BY primary_fm, phase ORDER BY retained_fragments DESC;

-- name: FDA "Fluid/Blood Leak" code vs the coded failure mode
SELECT primary_fm, COUNT(*) AS complaints,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct
FROM complaints WHERE fda_device_problems LIKE '%Leak%'
GROUP BY primary_fm ORDER BY complaints DESC;

-- name: Manufacturer conclusions: how often a cause was attributed to the device or to use
SELECT contributor, COUNT(*) AS complaints,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct
FROM complaints GROUP BY contributor ORDER BY complaints DESC;

-- name: Human review workload by reason
SELECT reason, COUNT(*) AS reports FROM review_queue GROUP BY reason ORDER BY reports DESC;
