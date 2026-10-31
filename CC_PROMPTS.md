# PayTime — Claude Code prompts

Run **P0 first**, commit, push. Everyone else pulls before starting.
Then P1, P2, P3 run in parallel in three separate Claude Code sessions.

**The one rule that keeps three sessions from fighting:** each prompt says which folder it owns and forbids touching anything else. Do not remove that line.

---

## P0 — Scaffold (Aryan, minute 0, ~10 min)

> Run this, check it, commit, push, tell the others to pull.

```
Scaffold a FastAPI + SQLite project called PayTime. It is an agent that
collects outstanding debts (udhaar) for small Indian merchants: the merchant
names who owes what, the agent calls the customer in their language, handles
the conversation, verifies payment against a transaction feed, and stops
chasing once settled.

Create exactly this structure and nothing more:

PayTime/
├── .gitignore
├── .env.example
├── requirements.txt
├── schema.sql
├── seed.py
├── app.py
├── db.py
├── agent/__init__.py
├── agent/routes.py
├── voice/__init__.py
├── voice/routes.py
├── verify/__init__.py
├── verify/routes.py
├── ui/index.html
└── demo/.gitkeep

schema.sql — exactly these tables, do not add or rename columns:

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

db.py — a single get_db() returning a sqlite3 connection with
row_factory = sqlite3.Row, pointing at state.db. Nothing else.

seed.py — drops and recreates from schema.sql, then inserts:
- 15 contacts with plausible Indian names, phone numbers, and language
  codes among 'hi', 'mr', 'ta'
- 6 debts across different stages and statuses, amounts 150 to 3000,
  created between 5 and 60 days ago
- 12 transactions as the mock Paytm merchant feed, all status SUCCESS,
  12-digit numeric refs. IMPORTANT: one transaction must exactly match
  debt id 1's amount and be timestamped 10 minutes ago, so the demo
  verification lands. The rest are noise with different amounts.

app.py — FastAPI app, CORS allow-all, serves ui/index.html at "/",
and does nothing else except:
    from agent.routes import router as agent_router
    from voice.routes import router as voice_router
    from verify.routes import router as verify_router
    app.include_router(agent_router)
    app.include_router(voice_router)
    app.include_router(verify_router)
Nobody edits app.py again after this commit.

Each routes.py is a stub: an APIRouter with the right prefix and a single
GET /ping returning {"ok": true}. Prefixes: /api/agent, /api/voice, /api/.

Implement these stubs ONLY as empty routers. The API contract below is for
the other sessions to fill in; put it in a comment block at the top of
each routes.py so each owner can see their own endpoints:

  agent/routes.py   (prefix /api/agent)
    POST /intake          {text}               -> created debt record
    POST /start_call      {debt_id}            -> {reply_text}
    POST /turn            {debt_id, utterance} -> {reply_text, intent, outcome}
    GET  /next_action/{debt_id}                -> {action, reason}

  voice/routes.py   (prefix /api/voice)
    POST /stt    multipart audio       -> {text}
    POST /tts    {text, language}      -> audio/wav bytes

  verify/routes.py  (prefix /api)
    GET  /debts                        -> list with contact name + status
    GET  /debts/{id}                   -> detail incl. contact_log
    POST /debts/{id}/approve_escalation
    POST /verify/screenshot  multipart image + debt_id
                                       -> {matched, confidence, transaction}
    POST /verify/check/{debt_id}       -> same shape, feed-only match

.gitignore: .env, *.db, *.db-journal, __pycache__/, *.pyc, voice/cache/,
.venv/, venv/, .DS_Store

.env.example with empty values: SARVAM_API_KEY=, LLM_API_KEY=

requirements.txt: fastapi, uvicorn, python-multipart, requests, python-dotenv

ui/index.html: single page, placeholder h1 only. Another session owns it.

Then run seed.py and confirm state.db is created with rows in every table.
Do not implement any business logic. This commit exists only to unblock
three people working in parallel.
```

> [!notes] Meri tipani
>

---

## P1 — Agent core (Aryan)

```
I am working in the PayTime repo. Read PROJECT.md and schema.sql first.

I own agent/ ONLY. Do not create or modify any file outside agent/.
Do not touch app.py, schema.sql, db.py, ui/, voice/, or verify/.
Use db.get_db() for all database access.

Build the conversation agent for a debt collection call. Four endpoints in
agent/routes.py, logic in separate modules:

agent/intake.py
  parse_intake(text) -> {contact_id, amount, confidence}
  Input is free-form Hinglish from the merchant, e.g.
  "Sharma ji ko 400 ka reminder bhejo" or "remind Patel 1200".
  Extract a name and an amount, fuzzy-match the name against the contacts
  table (difflib is fine), return the match. Handle Devanagari digits and
  words like "sau", "hazaar". If no confident name match, return
  candidates instead of guessing.

agent/conversation.py
  Builds the LLM system prompt carrying: merchant name (hardcode
  "Sharma General Store"), debtor name, amount, days overdue, current
  stage, language, and the full prior contact_log for this debt.

  Tone by stage: 0 gentle ("whenever convenient"), 1 firm (states amount
  and how overdue), 2 final (says the merchant will follow up personally).

  HARD RULES baked into the prompt, these are not optional:
  - First sentence of every call is exactly a disclosure that this is an
    automated reminder on behalf of the merchant, then confirms identity.
  - Never threaten legal action, credit consequences or public disclosure.
  - If the person says they are not the debtor, say NOTHING about the debt
    and end politely.
  - Never accuse anyone of lying about payment.
  Keep replies under 40 words. This is a phone call, not an essay.

agent/intents.py
  classify(utterance, context) -> one of:
  promise_to_pay | claims_paid | dispute_amount | refuse | wrong_number |
  callback_later | no_answer
  For promise_to_pay also extract the promised date, resolving relative
  dates like "kal", "Tuesday", "agle hafte" against today.
  Return structured JSON, never prose.

agent/state.py
  apply_outcome(debt_id, intent, extracted) -> updates debts.status,
  debts.stage, debts.next_action_at, writes contact_log, and inserts into
  promises on promise_to_pay.
  Transitions: promise_to_pay -> status 'promised', next_action_at =
  promised_date. claims_paid -> leave status, caller triggers verification.
  dispute_amount -> 'disputed', stop auto-chase. refuse -> flag for
  merchant, do NOT auto-advance stage. wrong_number -> 'opted_out'.
  Stage only advances 0->1 automatically; 1->2 requires an explicit
  approve_escalation call, which lives in another module.

agent/policy.py
  next_action(debt) -> {action, reason} where action is
  wait | sms | call_gentle | call_firm.
  For now a simple rule: nothing within 48h of last contact, escalate
  after 2 ignored contacts, never contact outside 9am-7pm, never contact
  a settled/disputed/opted_out debt. Keep the function signature stable,
  a learned policy may replace the body later.

LLM access: read LLM_API_KEY from env, put the provider call behind one
function in agent/llm.py so it can be swapped. If the key is missing,
fall back to deterministic canned responses so the rest of the app still
runs. Do not hardcode any key.

Write a small __main__ block in conversation.py that runs a fake call
end to end against seeded debt id 1, printing each turn, so I can test
without the UI or voice existing yet.
```

> [!notes] Meri tipani
>

---

## P2 — Voice pipeline (Hreday)

```
I am working in the PayTime repo, a debt-collection voice agent for Indian
merchants. Read PROJECT.md first.

I own voice/ ONLY. Do not create or modify any file outside voice/.
Do not touch app.py, schema.sql, db.py, agent/, verify/, or ui/index.html.

Build the speech layer using Sarvam AI. Read SARVAM_API_KEY from env,
never hardcode it.

voice/sarvam.py
  tts(text, language) -> wav bytes.  language is 'hi', 'mr' or 'ta'.
  stt(audio_bytes, language) -> transcript string.
  Use Sarvam's text-to-speech and speech-to-text endpoints. Look up the
  current request format from their docs rather than guessing field names.

  CRITICAL — credit budget is 1500 total across the team and re-testing
  the same line will burn it: cache every TTS result on disk in
  voice/cache/ keyed by sha256(text + language). Check the cache before
  every API call. Log a line whenever a real API call is made so I can
  watch consumption.

  Both functions must degrade gracefully: on any API error, log it and
  return None rather than raising, so a failed call never kills the demo.

voice/routes.py  (router already exists, prefix /api/voice, fill it in)
  POST /stt  multipart file upload -> {"text": "..."}
  POST /tts  {"text": ..., "language": ...} -> audio/wav response

voice/static/audio.js
  A small browser module, no framework, exporting:
    startRecording()  - getUserMedia, record until stopped
    stopRecording()   - returns a Blob
    sendForSTT(blob)  - POSTs to /api/voice/stt, returns text
    speak(text, lang) - POSTs to /api/voice/tts, plays the wav
  Handle a denied microphone permission by surfacing a clear message
  instead of failing silently. The demo laptop may not be the dev laptop.

voice/test_page.html
  A standalone page to exercise all of the above with no backend logic:
  a record button, a transcript display, a text box and a speak button,
  plus a language selector. I need to prove STT and TTS work in isolation
  before anything is wired to the agent.

Build and verify test_page.html works before touching routes.py.
Everything downstream depends on these two API calls actually working.
```

> [!notes] Meri tipani
>

---

## P3 — UI and verification (Akshat)

```
I am working in the PayTime repo, a debt-collection agent for Indian
merchants: the agent calls customers about outstanding udhaar, and when
the customer claims they paid, we verify it against the merchant's
transaction records instead of trusting them.

Read PROJECT.md and schema.sql first.

I own ui/ and verify/ ONLY. Do not create or modify any file outside
those two folders. Do not touch app.py, schema.sql, db.py, agent/, or
voice/. Use db.get_db() for database access.

--- verify/matcher.py ---

match_payment(debt_id, ref=None, screenshot_amount=None) -> dict

A UPI transaction does not say who it is from or what it is for. It has
an amount, a timestamp, a payer handle and a reference number. So matching
is a confidence ladder, not a yes/no:

  ref matches a transactions row exactly        -> "certain"
  contact.payer_handle matches + amount matches -> "certain"
  amount matches, within 60 min of last contact -> "high"
  amount matches, older or no recent contact    -> "ambiguous"
  nothing matches                               -> "none"

Return {matched, confidence, transaction, reason}.

Behaviour rules, these matter more than the code:
- "certain" and "high" settle the debt: status -> 'settled', write a
  contact_log row recording it, and if the payer_handle was previously
  unknown, store it on the contact so future matches are certain.
- "ambiguous" does NOT settle. It returns for merchant confirmation.
- "none" means unverified, NOT fraud. Never set any status implying the
  customer lied. The debt stays open and gets rechecked.

--- verify/ocr.py ---

read_screenshot(image_bytes) -> {amount, ref, timestamp, raw_text}

Send the image to a vision model and extract the fields from a UPI payment
screenshot. The reference number is the important one: it is what turns a
fuzzy amount-and-time guess into an exact row match. Return None for any
field that is not clearly present rather than guessing.

--- verify/routes.py (router exists, prefix /api, fill it in) ---

  GET  /debts                          list, joined with contact name,
                                       newest first, include days overdue
  GET  /debts/{id}                     detail with full contact_log and
                                       any promises
  POST /debts/{id}/approve_escalation  stage 1 -> 2 only, nothing else
  POST /verify/screenshot              multipart image + debt_id,
                                       runs ocr then matcher
  POST /verify/check/{debt_id}         matcher only, no screenshot

--- ui/index.html ---

Single self-contained page, vanilla JS, no build step, no npm. Inline CSS.

  - Debtor list: name, amount, days overdue, status badge
    (open / promised / settled / disputed), newest first
  - Click a debtor: transcript of what the agent said and what they
    replied, plus any promise made
  - "Approve escalation" button, only on stage 1
  - Screenshot upload with the verification result shown clearly:
    matched or not, the confidence level, and which transaction it hit
  - Header totals: outstanding vs recovered

This page is what is on the projector during the demo, so it carries more
weight than its difficulty suggests. Make the status flipping from
"chasing" to "settled" visually satisfying. Clean and legible beats
clever. Assume a projector: large text, high contrast.

Poll GET /debts every 3 seconds so the status change appears live during
the demo without anyone touching the page.
```

> [!notes] Meri tipani
>

---

## Order of operations

| When | Who | What |
|---|---|---|
| 0:00 | Aryan | P0, commit, push, tell the others |
| 0:05 | all | pull, `pip install -r requirements.txt`, `python seed.py` |
| 0:10 | all | P1, P2, P3 in parallel |
| 1:00 | Hreday | STT and TTS proven working in test_page.html, or raise the alarm |
| 4:00 | all | push everything, Aryan merges, run the loop end to end |
| 7:00 | Hreday | record the backup demo video |
| 7:15 | all | code freeze |

If Hreday's Sarvam calls are not working by hour 1, that is the moment to
decide whether the demo is voice or text. Do not let it slide to hour 4.

> [!notes] Meri tipani
>
