# PayTime — Merchant UI redesign (October 2026)

## What's new
- Restrained cream, forest green, and warm stone palette; no gradients, dark-blue sidebar, glows, or decorative orbs.
- Tighter merchant-facing copy and less crowded dashboard; IBM Plex Sans replaces the original rounded display face.
- Sign in / sign up / log out, with actual server-side sessions using HttpOnly cookies and salted scrypt password hashes.
- Demo workspace and independent merchant accounts: newly registered stores start with an empty ledger.
- New contact creation within the Add collection form, followed by collection intake.
- Old demo functionality retained: debt table, transcripts, escalation approval, screenshot verification, transaction feed, and settlement celebration.

## Quick start
Copy the contents of this folder into the existing PayTime repository. Do **not** overwrite teammates' `app.py`, `schema.sql`, or `seed.py` without coordination.

```bash
pip install -r requirements-ui.txt
python seed.py
python -m uvicorn app:app --reload
```
Open http://127.0.0.1:8000. Click **Open demo** to access the seeded Sharma General Store account, or **Create account** to set up an independent merchant workspace. Accounts are stored in a local `merchant_auth.db`, while each non-demo business has its own `merchant_data/merchant_<id>.db` file.

## Important integration boundaries
`app.py` mounts `auth.routes`, `ui.routes` and `verify.routes`, and uses a middleware that requires a valid merchant session for all `/api/ui/*` and `/api/verify/*` calls. This is important: simply including the routers in another `app.py` **without the middleware** would leave the endpoints unprotected and break account isolation. Ask the backend owner to port the middleware as well, and coordinate session checks for their agent/voice endpoints. Do not claim production-level authentication, PCI compliance, or Paytm identity verification from this prototype. It is a functional local hackathon auth demo, not an enterprise-ready Paytm login.

## Files changed
- `ui/index.html` — new auth page, simplified overview copy, form additions
- `ui/app.js` — auth flow, current merchant display, contact creation
- `ui/refresh.css` — fully new visual layer on top of existing stylesheet
- `ui/routes.py` — add contact endpoint and per-session merchant database context
- `verify/routes.py` — per-session merchant database context
- `auth/routes.py` — account store, passwords, sessions and merchant database provisioning
- `app.py` — mount auth, enforce merchant scope
- `.gitignore` — do not commit local merchant databases

## Design reference
Adapted general admin design principles from Shopify's September 2026 admin redesign: focus, directness, lighter interface frames and reducing unnecessary containers. This is a custom implementation, not a copy of the Shopify UI.
