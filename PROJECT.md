# Collection Agent — Project Truth

**Track 1: Merchant Growth AI — "Build the AI business partner for every Paytm merchant"**

Team: Aryan Daga, Hreday Shah, Akshat Chauhan
Build window: 8 hours
Project: **PayTime** — `git@github.com:akshat280706/PayTime.git`

---

## 1. What we are building

An agent that collects the money a merchant is owed, so the merchant never has to be the one asking.

The merchant tells the agent who owes what. The agent then runs the whole chase on its own: it calls the customer in their own language, holds an actual conversation, handles "I'll pay Tuesday", logs the promise, follows up on Tuesday, verifies the payment the moment it lands, and stops. The merchant approves escalation and otherwise does nothing.

**One-line pitch:** Paytm digitised the khata. We are automating the collection.

**Emotional hook, lead with this:** Udhaar does not go uncollected because merchants forget. It goes uncollected because calling Sharma ji about ₹400 is socially expensive. We are selling the removal of awkwardness, not automation.

> [!notes] Meri tipani
>

---

## 2. The competitive truth (everyone on the team must know this cold)

Do not walk into that room claiming reminders are new. They are not. Someone in that room built them.

**What already exists:**

| Product | What it does | Source |
|---|---|---|
| **Paytm Business Khata** | Udhaar/advance/cash ledger per customer, bill photos, reports, reminders by SMS and WhatsApp, one-click payment links | business.paytm.com/business-khata |
| **KhataBook** | Automated **IVR call** reminders for udhaar since **Oct 2021**. Nine Indian languages, call followed by SMS with payment link, bulk calling, collection dashboard, call history. 10M+ MAU | Press release, Oct 2021 |
| **OkCredit** | Same ledger + multi-language reminder pattern | okcredit.in |
| **DPDzero, DROS.ai** | AI voice collections in India, but sold to **lenders and NBFCs**, not to kirana merchants. DROS.ai led with compliance guardrails because of regulatory scrutiny | Industry press, 2026 |

**So what is actually ours:**

1. **KhataBook's is IVR.** A recorded message plays and that is it. It cannot handle "I'll pay Tuesday" or "I already sent it". Ours holds the conversation.
2. **Nobody closes the verification loop.** Today the debtor says "paid, see screenshot" and the merchant still checks by hand. We verify and auto-stop the chase.
3. **Nobody learns the escalation.** Everyone broadcasts on a fixed schedule or on demand. We learn channel, timing and firmness per debtor.

**How to open the pitch:** name Business Khata explicitly, then position on top of it. "Paytm already has the ledger. It still needs a human to work it. We built the agent that works it." Building on their product reads as homework done. Ignoring it reads as the opposite.

> [!notes] Meri tipani
>

---

## 3. The loop

```
  merchant speaks/types: "Sharma ji ko 400 ka reminder bhejo"
                              |
                     [INTAKE] parse name + amount
                      match against contacts
                              |
                     [POLICY] decide action:
                   wait / SMS / call / escalate tone
                              |
                      [VOICE] Sarvam TTS, call in their language
                              |
                      [AGENT] handle the reply:
            promise | dispute | already-paid | refuse | wrong number
                              |
                      [STATE] log outcome, schedule next action
                              |
                     [VERIFY] payment lands OR screenshot arrives
                              → match → settle → STOP CHASING
                              |
                         merchant sees it happened
```

The row that carries the whole pitch is **the reply**. Everything else is a degree of automation Paytm could ship next quarter. Handling the conversation, closing verification and learning escalation are structurally different from a send button. Spend the demo there.

> [!notes] Meri tipani
>

---

## 4. Scope

### IN (must work by hour 7)
- Conversational intake: merchant speaks or types, debtor record gets created
- Debtor conversation agent with intent extraction and guardrails
- Voice in and out via Sarvam, **browser-based**
- Verification by screenshot OCR + mock transaction feed
- Merchant UI: debtor list, status, transcripts, approve escalation
- Seeded demo data and a scripted run

### STRETCH (only after the loop is green)
- Learned escalation policy (bandit + simulator + one chart)
- Multi-language switching mid-demo
- Promise-to-pay follow-up firing on schedule

### OUT (do not build, do not mention as built)
- Churn detection, revenue trends, cash flow forecasting
- Real telephony
- Native Android app
- Real contact-book integration
- Real Paytm API integration

> [!notes] Meri tipani
>

---

## 5. The telephony decision (settled, do not relitigate)

**We have no telephony account and 8 hours. We are not placing real phone calls.**

Sarvam does speech in and speech out. It does not dial Indian phone numbers. Real calls need Exotel/Plivo/Knowlarity, and SMS needs DLT registration, which cannot be obtained inside a hackathon.

**What we build:** a browser-based voice conversation that runs the identical flow. Mic in, Sarvam STT, agent, Sarvam TTS, speaker out.

**What we say on stage, unprompted:** "The call runs in the browser today. Telephony is a provider swap, not a redesign — the agent, the policy and the verification are unchanged." Say it before anyone asks. Judges accept this. What they do not accept is finding it out by asking.

> [!notes] Meri tipani
>

---

## 6. Architecture

```
  ┌──────────────┐        ┌─────────────────┐        ┌──────────────┐
  │  Merchant UI │        │   Agent Core    │        │   Sarvam     │
  │  (browser)   │◄──────►│   (FastAPI)     │◄──────►│   STT / TTS  │
  └──────────────┘        └────────┬────────┘        └──────────────┘
         │                         │
         │                  ┌──────▼──────┐
         │                  │  SQLite     │
         │                  │  state.db   │
         │                  └──────┬──────┘
         │                         │
         │                  ┌──────▼──────────┐    ┌────────────────┐
         └─────────────────►│  Verification   │◄───│ mock txn feed  │
             screenshot     │  OCR + matcher  │    │  (CSV)         │
                            └─────────────────┘    └────────────────┘

                            ┌─────────────────┐
                            │ Escalation      │  trained offline,
                            │ policy (bandit) │  loaded as a function
                            └─────────────────┘
```

One FastAPI backend, one SQLite file, one browser frontend. No microservices, no queues, no Docker. Eight hours.

> [!notes] Meri tipani
>

---

## 7. Data model (freeze this before splitting up)

```sql
CREATE TABLE contacts (
  id INTEGER PRIMARY KEY,
  name TEXT,              -- "Sharma ji"
  phone TEXT,
  language TEXT           -- 'hi', 'mr', 'ta'
);

CREATE TABLE debts (
  id INTEGER PRIMARY KEY,
  contact_id INTEGER,
  amount REAL,
  created_at TEXT,
  due_date TEXT,
  stage INTEGER DEFAULT 0,      -- 0 gentle, 1 firm, 2 final
  status TEXT DEFAULT 'open',   -- open | promised | settled | disputed | opted_out
  next_action_at TEXT
);

CREATE TABLE contact_log (
  id INTEGER PRIMARY KEY,
  debt_id INTEGER,
  ts TEXT,
  channel TEXT,           -- call | sms
  stage INTEGER,
  transcript TEXT,
  outcome TEXT            -- see §8 intents
);

CREATE TABLE promises (
  id INTEGER PRIMARY KEY,
  debt_id INTEGER,
  promised_date TEXT,
  made_at TEXT,
  kept INTEGER DEFAULT 0
);

CREATE TABLE transactions (      -- the mock Paytm feed
  id INTEGER PRIMARY KEY,
  amount REAL,
  ts TEXT,
  ref TEXT,
  payer_handle TEXT,
  status TEXT             -- SUCCESS | FAILED
);
```

**Rule: nobody changes this schema after hour 1 without telling the other two.** Three people building against a moving data model is how 8-hour teams lose hour 5.

### Where the data actually lives

**Local SQLite file. No cloud database.**

A hosted DB (Supabase, Firebase, a Postgres instance) costs setup time you do not have and adds a network dependency at the exact moment you cannot afford one. Demoing against a cloud DB on conference wifi is a well-known way to lose.

**Dev workflow:**
- `schema.sql` and `seed.py` are committed to the repo. The `.db` file is **gitignored**.
- Each person runs `python seed.py` and gets their own identical local `state.db`.
- The shared artifact is the seed script, not the database. Never commit the binary `.db` — it conflicts on every pull.
- For the demo, one laptop runs the backend and the others point their browser at it over the local network, or simply run everything on that one machine.

If the project survives the hackathon, swapping SQLite for Postgres is a connection-string change, since nothing here uses SQLite-specific SQL. Say that if a judge asks about scale.

> [!notes] Meri tipani
>

---

## 8. Conversation design

### Agent system prompt must carry
Merchant name, debtor name, amount, days overdue, current stage, language, and the full history of previous contacts and promises.

### Opening line, every call, non-negotiable
> "Namaste, this is an automated reminder on behalf of [Merchant]. Is this [Name]?"

Disclosure in the first sentence. This is both an ethics requirement and a pitch asset.

### Intents to extract (this is the structured output)
| Intent | Meaning | What happens next |
|---|---|---|
| `promise_to_pay` | gave a date | log promise, schedule follow-up for that date, status → promised |
| `claims_paid` | says already paid | trigger verification, ask for screenshot if no match |
| `dispute_amount` | disagrees on amount | flag for merchant, stop auto-chase |
| `refuse` | will not pay | escalate to merchant, do not auto-escalate tone |
| `wrong_number` | not the debtor | **say nothing about the debt**, mark bad number, stop |
| `callback_later` | asked to call later | reschedule, do not count as contact attempt |
| `no_answer` | no pickup | reschedule per policy |

### Tone ladder
- **Stage 0 (gentle):** "Just a reminder, whenever convenient."
- **Stage 1 (firm):** states the amount and how long it has been outstanding.
- **Stage 2 (final):** says the merchant will follow up personally. **Never threaten.** No legal language, no consequences we cannot carry out.

**Stage 1 → 2 requires merchant approval in the UI.** The agent never escalates to final on its own.

### Hard guardrails
1. Never reveal the debt to someone who is not the debtor
2. Never threaten legal action, credit consequences, or public disclosure
3. Calling hours 9am–7pm only
4. Opt-out honoured immediately and permanently
5. Every call logged with full transcript

These are five small features that are disproportionately valuable in the pitch. Build them, then say you built them.

> [!notes] Meri tipani
>

---

## 9. Escalation policy (the RL component) — STRETCH

**Formulation: contextual bandit.** Not deep RL, and say so. Overclaiming here is how you lose an RL-literate judge.

- **Context:** days overdue, amount, number of prior contacts, promises made, promises kept, last outcome, days since last contact
- **Actions:** `wait` | `sms` | `call_gentle` | `call_firm`
- **Reward:** `+amount` on payment, `−1` per contact made (cost and annoyance), `−20` on opt-out (relationship damage)

The negative terms matter. Without them the policy learns to call every day, which is exactly the behaviour that makes merchants lose customers.

**Training:** offline, in a synthetic simulator. Debtor personas with a response propensity, a fatigue curve, and a payment probability that rises with contact but falls after over-contact.

**Deliverable:** one chart. Recovered amount vs number of contacts, learned policy against a fixed-schedule baseline. That single chart is the entire RL pitch.

**What to say when asked "why not just dynamic programming?"** — and you will be asked:
> "For a fixed known demand distribution, DP would be correct and RL would be overkill. We use a bandit because the response dynamics are unknown and vary per debtor, so we learn them from contact history rather than assuming them."

That is true. Do not claim more than that.

**What to say about training data, unprompted:**
> "The policy is trained in a simulator, not on live debtors. We have no live debtors."

Name your own limitation before a judge does. It costs nothing and it reads as maturity.

> [!notes] Meri tipani
>

---

## 10. Verification (this is where ReceiptShield lives now)

Two paths into the same matcher.

**Path A — transaction feed.** Mock CSV of merchant transactions. Match on amount within a time window. On match: status → settled, chase stops, merchant notified.

**Path B — screenshot.** The debtor replies "paid, see screenshot" to get the agent off their back. Run the image through a vision model, pull amount / reference / timestamp, match against the feed.

**The rule that must be stated on the architecture slide and out loud:**
> OCR reads the claim. The transaction record decides. A screenshot is a claim, not proof.

If the screenshot matches no transaction, the outcome is **unverified**, not **fraud**. Never auto-accuse. The agent says it could not confirm yet and schedules a recheck.

> [!notes] Meri tipani
>

---

## 11. Stack

| Layer | Choice | Why |
|---|---|---|
| Backend | Python + FastAPI | fastest to stand up, everyone knows it |
| DB | SQLite | one file, zero setup |
| Frontend | Single HTML page + vanilla JS or React via CDN | no build step, no npm hell at hour 6 |
| Voice | Sarvam STT + TTS | the credits, and genuine Indian language quality |
| LLM | whatever key we have | conversation + intent extraction |
| OCR | vision model call | 20 lines, beats wiring Tesseract |
| Bandit | numpy, hand-rolled | a contextual bandit is 40 lines, do not import a framework |

**Sarvam credits: 500 each, 1500 total. Cache every TTS output during development.** Burning 1500 credits re-testing the same greeting line two hundred times is a real way to lose this.

> [!notes] Meri tipani
>

---

## 12. Work split

### Aryan — agent core and critical path
- **Hour 0–0.5:** build the schema and seed the DB. Commit it. Tell the others it is frozen. *Everyone is blocked until this exists, so it is first and it is fast.*
- **Hour 0.5–3:** conversation agent — system prompt, turn handling, intent extraction into structured outcomes, state transitions, guardrails from §8
- **Hour 3–4:** intake parser (free text/speech → name + amount → fuzzy match against contacts)
- **Hour 4–5.5:** integration — wire Hreday's voice to the agent, Akshat's UI to the state
- **Hour 5.5–7:** bandit + simulator + the chart, **only if the loop is green.** If it is not, this gets cut and you keep integrating.

### Hreday — voice pipeline
- **Hour 0–1:** Sarvam account, keys, a working TTS call and a working STT call in isolation. Prove both before building anything on top.
- **Hour 1–3:** browser audio — mic capture, send to backend, play response. This is fiddlier than it sounds, which is why it is a whole workstream.
- **Hour 3–4.5:** both directions wired: merchant speaks intake, agent speaks to debtor. Language switching by debtor record.
- **Hour 4.5–6:** TTS caching layer, latency trimming, error handling for when the mic permission is denied on the demo laptop
- **Hour 6–7:** **record the backup demo video.** Non-negotiable, see §13.

### Akshat — UI, verification, demo
- **Hour 0–0.5:** wait for the schema, sketch screens on paper meanwhile
- **Hour 0.5–3:** merchant UI — debtor list with amounts and status, conversation transcripts, approve-escalation button, recovered vs outstanding summary
- **Hour 3–4:** verification — screenshot upload, vision call, matcher against the mock feed, settle-and-stop
- **Hour 4–5:** seed data — 15 plausible contacts, 6 open debts at different stages, a mock transaction feed that contains the payment the demo debtor will make
- **Hour 5–7:** polish. This is what is on the projector, so it carries weight beyond its difficulty. Make the status change from "chasing" to "settled" visibly satisfying.

### All three
- **Hour 7–8:** demo rehearsal, twice end to end, then stop touching the code.

### Cut ladder (if behind)
1. Bandit goes first
2. Then multi-language switching, demo in Hindi only
3. Then screenshot path, keep transaction-feed matching
4. **Never cut:** the conversation, the verification stop, the UI

> [!notes] Meri tipani
>

---

## 13. Demo script (3 minutes)

1. **The hook, 20 seconds.** "Every kirana merchant is owed money they will never chase, because calling someone about ₹400 is awkward. Paytm already gives them the ledger. It still needs a human to work it."
2. **Intake, 25 seconds.** Merchant speaks Hinglish into the app: *"Sharma ji ko 400 ka reminder bhejo."* Record appears in the list.
3. **The call, 60 seconds.** Agent calls, discloses it is automated, asks for the payment. Debtor (a teammate on mic) says *"paisa bhej diya hai"* — claims paid. Agent asks for confirmation.
4. **Verification, 30 seconds.** Screenshot gets sent. OCR reads it. It matches the transaction feed. Status flips to settled. **The chase stops by itself.** This is the money shot — let it land, do not talk over it.
5. **The policy, 25 seconds.** One chart. Learned policy recovers more with fewer contacts than a fixed schedule. "Trained in simulation, not on live debtors."
6. **The honest close, 20 seconds.** "Calls run in the browser today, telephony is a provider swap. KhataBook has had IVR reminders since 2021 — what they cannot do is hold the conversation, confirm the payment, or learn when to push."

**Backup video recorded by hour 7.** Live voice demos fail often enough that you want the recording cued up while you try it live.

> [!notes] Meri tipani
>

---

## 14. Open decisions

**Name: settled, PayTime.** One note and then drop it: the name sits close to "Paytm" by ear. At their own hackathon that reads as on-theme, so it is fine here. It would need a rethink before anything ships publicly. Not a hackathon problem, do not spend a minute on it today.

**Verify the Paytm comparison yourself.** Everything in §2 about Business Khata comes from their public page, and a page not mentioning a feature is not proof the feature is absent. Install the app, check what reminders actually do today. Getting one row wrong costs the whole table's credibility, in front of the people who built it.

> [!notes] Meri tipani
>

---

## 15. Git

`git@github.com:akshat280706/PayTime.git` — Akshat owns the repo, Aryan owns the health of `main` since he is doing integration.

### The rule that actually prevents merge hell

**Ownership by directory, not by branch.** Conflicts happen when two people edit the same file, and no branching strategy saves you from that. If each person's code lives in their own folder, you can push to `main` all day and barely conflict.

```
PayTime/
├── README.md
├── PROJECT.md
├── .gitignore
├── .env.example          # committed, with empty values
├── requirements.txt
├── schema.sql            # frozen after hour 1
├── seed.py
├── app.py                # routes only — SHARED, see below
├── agent/                # ARYAN
│   ├── conversation.py
│   ├── intents.py
│   ├── intake.py
│   └── state.py
├── voice/                # HREDAY
│   ├── sarvam.py
│   ├── routes.py
│   └── cache/            # gitignored
├── ui/                   # AKSHAT
│   ├── index.html
│   ├── app.js
│   └── style.css
├── verify/               # AKSHAT
│   ├── ocr.py
│   ├── matcher.py
│   └── routes.py
├── policy/               # ARYAN, stretch
│   ├── simulator.py
│   ├── bandit.py
│   └── train.py
└── demo/
    ├── seed_data.json
    └── screenshots/
```

**`app.py` is the only shared file, so it is the only real conflict risk.** Kill it: each person puts their endpoints in their own `routes.py` and `app.py` does nothing but `include_router()` for all three. Write those three include lines in the first commit, then nobody touches `app.py` again.

### .gitignore (commit this first)

```
.env
*.db
*.db-journal
__pycache__/
*.pyc
voice/cache/
.venv/
venv/
.DS_Store
```

**Never commit `state.db`.** A binary file conflicts on every single pull and there is no resolving it. The seed script is the shared artifact.

### Secrets

Sarvam and LLM keys go in `.env`, which is gitignored. Commit `.env.example` with the key names and empty values so the others know what to set.

**A leaked Sarvam key can burn all 1500 credits before you notice.** If one gets pushed by accident, rotate it immediately — deleting the commit does not help, it is already in the history and on GitHub's servers.

### Cadence

- Commit every ~30 minutes, push every hour. Small commits, present-tense messages.
- Pull before you push. Always.
- **Hour 4 is the first integration checkpoint.** All three push, Aryan merges, the loop gets run end to end even if it is ugly. If integration first happens at hour 7, you do not have a demo.
- **Hour 7:15 is the code freeze.** After that, nothing but demo-breaking fixes. No refactors, no "quick improvements", no renaming variables. The number of hackathon demos killed by a confident commit at minute 470 is high.

### If something breaks badly near the end

`git stash` or branch off, do not try to fix forward on `main` under time pressure. Having a known-good commit you can reset to is the whole reason you are committing every 30 minutes.

> [!notes] Meri tipani
>

---

## 16. Questions judges will ask

| Question | Answer |
|---|---|
| "KhataBook has had this since 2021." | "They have IVR. A recording plays. It cannot handle 'I'll pay Tuesday', and it cannot tell you when the person actually paid." |
| "Why not just use Business Khata reminders?" | "Those need a human to decide who to chase and to check whether they paid. We close both ends." |
| "Won't this damage customer relationships?" | "That is why the merchant holds the dial. Gentle by default, escalation requires their approval, and the policy is penalised for opt-outs." |
| "Is this legal?" | "Transactional communication to someone with an existing relationship, with disclosure in the first sentence, calling hours, and opt-out honoured. We built the guardrails before the features." |
| "Why RL and not a rule?" | See §9. Do not overclaim. |
| "Did you train on real data?" | "No. Simulator. We have no live debtors." |

> [!notes] Meri tipani
>
