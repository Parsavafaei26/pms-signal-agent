-- Signal checks run by the agent. Each block starts with "-- name: <check>".
-- Parameters (sqlite named params): :min_count, :ratio, :cluster_min
-- Thresholds are set in agent/config.py BEFORE looking at results and are reported with every run.

-- name: rising_failure_mode
-- Rolling 4-quarter window vs the previous 4 quarters, per failure mode (unique complaints).
-- Flag when the current window has at least :min_count complaints AND is at least :ratio times
-- the previous window (a previous window of 0 is treated as 1).
WITH q AS (
    SELECT quarter, ROW_NUMBER() OVER (ORDER BY quarter) AS qi
    FROM (SELECT DISTINCT quarter FROM reports WHERE in_sample = 1)
),
counts AS (
    SELECT c.primary_fm, q.qi, COUNT(*) AS n
    FROM complaints c JOIN q USING (quarter)
    GROUP BY c.primary_fm, q.qi
),
fm AS (SELECT code AS primary_fm FROM failure_modes),
windows AS (
    SELECT fm.primary_fm, q.quarter, q.qi,
           (SELECT COALESCE(SUM(n),0) FROM counts c WHERE c.primary_fm = fm.primary_fm
              AND c.qi BETWEEN q.qi - 3 AND q.qi)     AS current_n,
           (SELECT COALESCE(SUM(n),0) FROM counts c WHERE c.primary_fm = fm.primary_fm
              AND c.qi BETWEEN q.qi - 7 AND q.qi - 4) AS baseline_n
    FROM fm CROSS JOIN q
    WHERE q.qi >= 8                                   -- need two full windows
)
SELECT quarter AS period, primary_fm AS subject, current_n, baseline_n,
       printf('%d complaints in the 4 quarters to %s vs %d in the 4 before', current_n, quarter, baseline_n) AS detail
FROM windows
WHERE current_n >= :min_count
  AND current_n >= :ratio * MAX(baseline_n, 1)
ORDER BY quarter, primary_fm;

-- name: serious_event
-- Individual review, not a trend: every critical/catastrophic event, retained fragment or harm to a user.
SELECT quarter AS period, report_number AS subject, NULL AS current_n, NULL AS baseline_n,
       printf('%s %s%s%s', primary_fm, severity,
              CASE WHEN retained_fragment = 1 THEN ', retained fragment' ELSE '' END,
              CASE WHEN user_harm = 1 THEN ', user harm' ELSE '' END) AS detail
FROM complaints
WHERE severity IN ('S4','S5') OR retained_fragment = 1 OR user_harm = 1
ORDER BY quarter, report_number;

-- name: keyword_cluster
-- Component-level clusters that failure-mode codes are too coarse to show.
-- Counts unique complaints per quarter whose narrative matches any pattern of a watchlist group.
SELECT c.quarter AS period, w.term_group AS subject, COUNT(DISTINCT c.report_number) AS current_n,
       NULL AS baseline_n,
       printf('%d complaints mention %s in %s', COUNT(DISTINCT c.report_number), w.term_group, c.quarter) AS detail
FROM complaints c
JOIN keyword_watchlist w ON UPPER(c.event_description) LIKE w.pattern
GROUP BY c.quarter, w.term_group
HAVING COUNT(DISTINCT c.report_number) >= :cluster_min
ORDER BY c.quarter, w.term_group;

-- name: share_shift
-- EXPLORATORY: added after the first run, because the count-ratio rule above missed the gradual
-- rise of catheter body breaks seen in project 1. Compares each failure mode's SHARE of all
-- complaints in the current 4 quarters with the previous 4. Flag when the share rises by at least
-- :share_points percentage points and the current window has at least :share_min complaints.
WITH q AS (
    SELECT quarter, ROW_NUMBER() OVER (ORDER BY quarter) AS qi
    FROM (SELECT DISTINCT quarter FROM reports WHERE in_sample = 1)
),
c AS (SELECT primary_fm, qi FROM complaints JOIN q USING (quarter)),
w AS (
    SELECT q.quarter, q.qi, fm.code AS primary_fm,
           (SELECT COUNT(*) FROM c WHERE c.primary_fm = fm.code AND c.qi BETWEEN q.qi-3 AND q.qi)   AS cur_n,
           (SELECT COUNT(*) FROM c WHERE c.qi BETWEEN q.qi-3 AND q.qi)                              AS cur_tot,
           (SELECT COUNT(*) FROM c WHERE c.primary_fm = fm.code AND c.qi BETWEEN q.qi-7 AND q.qi-4) AS base_n,
           (SELECT COUNT(*) FROM c WHERE c.qi BETWEEN q.qi-7 AND q.qi-4)                            AS base_tot
    FROM q CROSS JOIN failure_modes fm
    WHERE q.qi >= 8
)
SELECT quarter AS period, primary_fm AS subject, cur_n AS current_n, base_n AS baseline_n,
       printf('share %.0f%% vs %.0f%% (%+.0f points)', 100.0*cur_n/cur_tot, 100.0*base_n/base_tot,
              100.0*cur_n/cur_tot - 100.0*base_n/base_tot) AS detail
FROM w
WHERE cur_n >= :share_min
  AND 100.0*cur_n/cur_tot - 100.0*base_n/base_tot >= :share_points
ORDER BY quarter, primary_fm;
