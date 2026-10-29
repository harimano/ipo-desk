-- Each reader's own saved dashboard (worker.js handleApi): one row per signed-in email and part.
-- The Worker runs this statement itself the first time it needs the table (CREATE TABLE IF NOT EXISTS), so nothing
-- has to be pasted into the D1 console; it is here so the shape is readable and so a console session can run it by hand.
CREATE TABLE IF NOT EXISTS user_state (
  email   TEXT NOT NULL,   -- the verified Access email, lower-cased; never a value the browser sent
  part    TEXT NOT NULL,   -- holdings | interest | apps | tasks-done | tasks-custom | investors | theme
  body    TEXT NOT NULL,   -- the part's whole JSON value (a few KB at most; 64 KB cap)
  updated TEXT NOT NULL,   -- ISO time of the last PUT
  PRIMARY KEY (email, part)
);
