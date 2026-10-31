# PayTime — Akshat's UI + verification package

A working merchant dashboard for the 8-hour PayTime hackathon, built using static HTML/CSS/JS and two FastAPI routers. No Node/npm build step, and no actual phone calls.

## Run locally

```bash
python -m pip install -r requirements-ui.txt
python seed.py
python -m uvicorn app:app --reload
```
Open `http://127.0.0.1:8000`.

### Live vision verification
Set `OPENAI_API_KEY` in the server environment (never in the frontend). The screenshot OCR calls the vision model through the OpenAI API. **Without a key, the included exact sample receipt uses a clearly identified deterministic demo extractor** (matched by image SHA-256); every other image requires real vision OCR and produces a configuration error if no key is present. The sample is synthetic and still requires a matching successful SQLite transaction for settlement. The mock transaction feed is local SQLite; no Paytm integration is claimed.

Sample screenshot: `demo/screenshots/sharma-payment.png`. Select **Sharma ji**, upload screenshot and press **Verify**. It contains ₹400 / reference `UPI-DEMO-400-1026`, matching the seeded SUCCESS ledger entry. The API settles that one debt, logs proof, and nulls its next scheduled action. The bundled sample is recognized by a deterministic fixture matcher for demo reliability; real receipts use the vision model.

## Integrate with Aryan's shared app.py

```python
from ui.routes import router as ui_router
from verify.routes import router as verify_router
from fastapi.staticfiles import StaticFiles
app.include_router(ui_router)
app.include_router(verify_router)
app.mount('/ui', StaticFiles(directory='ui'), name='ui')
```

Do not overwrite your team's existing `app.py`, `schema.sql`, or `seed.py` without comparing. The provided schema follows PROJECT.md; seed.py is idempotent and can be merged with Aryan's seed data. Set `PAYTIME_DB` to the same SQLite file all routers use.

### Contract
- `GET /api/ui/dashboard` returns `{contacts, debts, logs, summary}`.
- `POST /api/ui/debts/{id}/approve-escalation` approves `stage=1 → 2` only, and logs authorization.
- `POST /api/ui/intake` accepts `{text, contact_id?, amount?}`. This is a simplified fallback; Aryan can replace it with the agent's parser.
- `GET /api/verify/transactions` returns mock successful and unsuccessful transactions (the UI shows successful only).
- `POST /api/verify/screenshot` is multipart `{debt_id, file}`. OCR extracts `{amount, reference, timestamp}`; matcher requires a successful unused transaction with exact reference and amount, and a reasonable timestamp. Successful verification updates `status=settled` and `next_action_at=NULL`.

### Voice handoff
The drawer's **Open browser voice demo** button is intentionally a non-deceptive placeholder. Have Hreday expose a documented browser voice start action or a route, and connect it in `ui/app.js` in `handleClick` for `data-call-id`. The dashboard is otherwise functional without Sarvam credentials.

### Demo sequence
1. Open demo controls → Sharma ji; show recorded call transcript and ₹400 in chasing state.
2. Have teammate demonstrate a live browser voice exchange through Hreday's integration.
3. Verification → select Sharma ji → upload `demo/screenshots/sharma-payment.png` → verify. Result changes to settled; activity log says chase stopped; recovered/outstanding totals update.
4. Priya Patel's firm-stage collection shows the merchant approval control. Try it to demonstrate human-in-the-loop.
5. For a fresh show: delete `state.db`, run `python seed.py`, restart server. The seed script refuses to overwrite real changes.

### Important safety limitations
This is a demo, not a production debt collection product. The UI does not itself enforce calling hours, opt-outs, debtor identity, or all agent guardrails; Aryan's agent must enforce them server-side. OCR extraction is not proof. Every settlement requires successful ledger match. Identical-amount transactions without a unique transaction reference do not verify. No real telephony/Paytm API integration. Never use real private customer data in demo seed files.
