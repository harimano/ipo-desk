-- Each reader's own saved dashboard (worker.js handleApi): one row per signed-in email and part.
-- The Worker runs this statement itself the first time it needs the table (CREATE TABLE IF NOT EXISTS), so nothing
-- has to be pasted into the D1 console; it is here so the shape is readable and so a console session can run it by hand.
CREATE TABLE IF NOT EXISTS user_state (
  email   TEXT NOT NULL,   -- the verified Access email, lower-cased; never a value the browser sent
  part    TEXT NOT NULL,   -- holdings | interest | apps | tasks-done | tasks-custom | investors | theme | budget
  body    TEXT NOT NULL,   -- the part's whole JSON value (a few KB at most; 64 KB cap)
  updated TEXT NOT NULL,   -- ISO time of the last PUT
  PRIMARY KEY (email, part)
);

-- "Wrong number?" (site/src/report.js → POST /api/report): a reader flags a figure; Hari reads them on /admin.
-- A report never changes a number. Capped at 20 a reader a day. `status` is for Hari ('open' → 'done'), by hand in the console.
CREATE TABLE IF NOT EXISTS reports (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  at         TEXT NOT NULL,   -- ISO time the Worker received it
  email      TEXT NOT NULL,   -- the verified Access email of the reader
  issue      TEXT NOT NULL,   -- the IPO's row name
  ig_id      TEXT,            -- its InvestorGain id, when the row has one
  field      TEXT NOT NULL,   -- gmp | book | retail | qib | band | dates | odds | status | other
  shown      TEXT,            -- the value on screen at the time
  note       TEXT,            -- what the reader typed (500 chars)
  page       TEXT,
  data_as_of TEXT,            -- meta.asOf of the document the page was showing
  status     TEXT NOT NULL DEFAULT 'open'
);

-- Daily active readers (worker.js noteDailyActive → /admin/retention.json, the "Readers by week" card): one row per
-- reader per IST day, written on a page load. No email: email_hash = SHA-256(DAU_SALT + "\n" + email), the salt a
-- Worker secret handed over by deploy.yml. Without the secret nothing is written. Counts only, ever.
CREATE TABLE IF NOT EXISTS daily_active (
  day        TEXT NOT NULL,   -- YYYY-MM-DD in IST
  email_hash TEXT NOT NULL,   -- hex SHA-256 of salt + newline + lower-cased email
  PRIMARY KEY (day, email_hash)
);
