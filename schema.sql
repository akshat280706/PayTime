CREATE TABLE contacts (
  id INTEGER PRIMARY KEY, name TEXT, phone TEXT, language TEXT,
  payer_handle TEXT
);
CREATE TABLE debts (
  id INTEGER PRIMARY KEY, contact_id INTEGER, amount REAL,
  created_at TEXT, due_date TEXT, stage INTEGER DEFAULT 0,
  status TEXT DEFAULT 'open', next_action_at TEXT
);
CREATE TABLE contact_log (
  id INTEGER PRIMARY KEY, debt_id INTEGER, ts TEXT, channel TEXT,
  stage INTEGER, transcript TEXT, outcome TEXT
);
CREATE TABLE promises (
  id INTEGER PRIMARY KEY, debt_id INTEGER, promised_date TEXT,
  made_at TEXT, kept INTEGER DEFAULT 0
);
CREATE TABLE transactions (
  id INTEGER PRIMARY KEY, amount REAL, ts TEXT, ref TEXT,
  payer_handle TEXT, status TEXT
);
