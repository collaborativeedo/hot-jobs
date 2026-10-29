-- Lane County Hot Jobs traffic counter. No cookies, no IP addresses stored.
CREATE TABLE IF NOT EXISTS daily (
  day TEXT NOT NULL, host TEXT NOT NULL, event TEXT NOT NULL, label TEXT NOT NULL DEFAULT '', n INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (day, host, event, label)
);
-- One row per anonymous daily visitor key per site and event; deleted after 35 days.
CREATE TABLE IF NOT EXISTS visitors (
  day TEXT NOT NULL, host TEXT NOT NULL, event TEXT NOT NULL, v TEXT NOT NULL,
  PRIMARY KEY (day, host, event, v)
);
