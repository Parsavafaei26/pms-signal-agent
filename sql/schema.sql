-- PMS signal agent: SQLite schema
-- One row per MAUDE report; one current label per report; every agent action logged.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS reports (
    report_number        TEXT PRIMARY KEY,
    date_received        TEXT NOT NULL,          -- YYYYMMDD
    quarter              TEXT NOT NULL,          -- e.g. 2024-Q3
    event_type           TEXT,                   -- Malfunction / Injury / Death
    brand_name           TEXT,
    manufacturer         TEXT,
    product_code         TEXT,
    fda_device_problems  TEXT,
    fda_patient_problems TEXT,
    event_description    TEXT,
    manufacturer_narrative TEXT,
    in_scope             INTEGER NOT NULL DEFAULT 1,   -- 0 = excluded (e.g. midline catheter)
    in_sample            INTEGER NOT NULL DEFAULT 0    -- 1 = in the coding queue
);

-- Controlled vocabularies (what the validator and the SQL checks agree on)
CREATE TABLE IF NOT EXISTS failure_modes (
    code  TEXT PRIMARY KEY,
    name  TEXT NOT NULL,
    fmea_row TEXT                                   -- reference FMEA row, NULL = gap
);

CREATE TABLE IF NOT EXISTS labels (
    report_number     TEXT PRIMARY KEY REFERENCES reports(report_number),
    primary_fm        TEXT NOT NULL REFERENCES failure_modes(code),
    secondary_fm      TEXT,                          -- NULL = none
    phase             TEXT NOT NULL CHECK (phase IN ('P1','P2','P3','P4','P5')),
    severity          TEXT NOT NULL CHECK (severity IN ('S1','S2','S3','S4','S5')),
    contributor       TEXT NOT NULL CHECK (contributor IN ('DEV','USE','PAT','UNK')),
    retained_fragment INTEGER NOT NULL CHECK (retained_fragment IN (0,1)),
    user_harm         INTEGER NOT NULL CHECK (user_harm IN (0,1)),
    complaint_group   TEXT NOT NULL,                 -- reports of one complaint share this
    confidence        TEXT NOT NULL CHECK (confidence IN ('high','medium','low')),
    quote             TEXT,
    note              TEXT,
    voided            INTEGER NOT NULL DEFAULT 0,    -- manufacturer voided the report as duplicate
    coder             TEXT NOT NULL,                 -- e.g. replay:v1.1 or claude:<model>
    rules_version     TEXT NOT NULL,
    coded_at          TEXT NOT NULL,
    review_status     TEXT NOT NULL DEFAULT 'not_required'
                      CHECK (review_status IN ('not_required','pending','accepted','corrected'))
);

CREATE TABLE IF NOT EXISTS review_queue (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    report_number TEXT NOT NULL REFERENCES reports(report_number),
    reason        TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    resolved      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS keyword_watchlist (
    term_group TEXT NOT NULL,      -- e.g. septum_leak
    pattern    TEXT NOT NULL,      -- SQL LIKE pattern, upper case
    PRIMARY KEY (term_group, pattern)
);

CREATE TABLE IF NOT EXISTS signals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT NOT NULL,
    check_name  TEXT NOT NULL,     -- rising_failure_mode / serious_event / keyword_cluster
    period      TEXT,
    subject     TEXT NOT NULL,     -- failure mode, report number or term group
    current_n   INTEGER,
    baseline_n  INTEGER,
    detail      TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT NOT NULL,
    ts          TEXT NOT NULL,
    step        TEXT NOT NULL,     -- load / code / validate / route / signal / report
    report_number TEXT,
    outcome     TEXT NOT NULL,     -- ok / rejected / retry / flagged / error
    detail      TEXT
);

-- One row per unique complaint: drops voided duplicates and keeps the first report of each group.
CREATE VIEW IF NOT EXISTS complaints AS
SELECT l.*, r.quarter, substr(r.quarter, 1, 4) AS year, r.event_description, r.manufacturer_narrative,
       r.fda_device_problems
FROM labels l
JOIN reports r USING (report_number)
WHERE l.voided = 0
  AND l.report_number = (
        SELECT MIN(l2.report_number) FROM labels l2
        WHERE l2.complaint_group = l.complaint_group AND l2.voided = 0);
