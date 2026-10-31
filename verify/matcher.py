"""Transaction-ledger verification. OCR is never sufficient by itself."""
import sqlite3
from datetime import datetime, timedelta

WINDOW_DAYS = 14


def match_transaction(conn: sqlite3.Connection, *, debt_id: int, amount: float, reference: str = "", timestamp: str = ""):
    """Return a successful, unused ledger transaction or None.

    Amount must match exactly to paise. Reference must match whenever supplied.
    A receipt timestamp, if parsed, must be within 14 days of the ledger entry.
    Also rejects ledger references already used to settle another debt.
    """
    debt = conn.execute("SELECT id, amount, status, created_at FROM debts WHERE id=?", (debt_id,)).fetchone()
    if not debt or debt[2] in ('settled', 'opted_out') or round(float(debt[1])*100) != round(float(amount)*100):
        return None
    txns = conn.execute("SELECT id, amount, ts, ref, payer_handle FROM transactions WHERE status='SUCCESS'").fetchall()
    for t in txns:
        txid, txamount, txtime, txref, handle = t
        if round(float(txamount)*100) != round(float(amount)*100):
            continue
        if not reference or str(reference).strip().lower() != str(txref).strip().lower():
            # Amount-only screenshot claims must not settle another person's identical debt.
            continue
        try:
            ledger_dt = datetime.fromisoformat(txtime.replace('Z', '+00:00')).replace(tzinfo=None)
            if timestamp:
                receipt_dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00')).replace(tzinfo=None)
                if abs((ledger_dt-receipt_dt).total_seconds()) > WINDOW_DAYS*86400:
                    continue
            created = datetime.fromisoformat(debt[3].replace('Z', '+00:00')).replace(tzinfo=None)
            if ledger_dt < created - timedelta(days=1):
                continue
        except (ValueError, TypeError):
            continue
        # Persist a unique link in contact_log outcome: verified:REF
        used=conn.execute("SELECT 1 FROM contact_log WHERE outcome=? AND debt_id<>?", ('verified:'+txref,debt_id)).fetchone()
        if used:
            continue
        return {'id': txid,'amount': txamount,'ts':txtime,'ref':txref,'payer_handle':handle}
    return None


def match_feed_transaction(conn: sqlite3.Connection, *, debt_id: int):
    """Feed-only check (no screenshot, so no reference). Confidence ladder over successful, unused ledger entries
    with exactly the debt's amount:
      certain    contact's payer_handle is known and matches the payer, inside the time window
      high       payer_handle unknown on either side, inside the window (one candidate only)
      ambiguous  outside the window, or several equally good candidates: NOT settled, goes to merchant review
    A known handle that differs from the payer is someone else's payment and is skipped.
    Window = not earlier than a day before the debt was created.
    Returns {'confidence', 'transaction'} or None. Only certain/high may be settled."""
    debt = conn.execute("SELECT d.amount, d.status, d.created_at, c.payer_handle FROM debts d "
                        "LEFT JOIN contacts c ON c.id = d.contact_id WHERE d.id=?", (debt_id,)).fetchone()
    if not debt or debt[1] in ('settled', 'opted_out'):
        return None
    known = (debt[3] or '').strip().lower()
    created = datetime.fromisoformat(debt[2].replace('Z', '+00:00')).replace(tzinfo=None)
    found = {'certain': [], 'high': [], 'ambiguous': []}
    for txid, txamount, txtime, txref, handle in conn.execute(
            "SELECT id, amount, ts, ref, payer_handle FROM transactions WHERE status='SUCCESS' ORDER BY ts"):
        if round(float(txamount)*100) != round(float(debt[0])*100):
            continue
        if conn.execute("SELECT 1 FROM contact_log WHERE outcome=?", ('verified:'+txref,)).fetchone():
            continue
        payer = (handle or '').strip().lower()
        if known and payer and payer != known:
            continue  # a different, known payer: not evidence for this debt
        inside = datetime.fromisoformat(txtime.replace('Z', '+00:00')).replace(tzinfo=None) >= created - timedelta(days=1)
        level = ('certain' if known and payer else 'high') if inside else 'ambiguous'
        found[level].append({'id': txid, 'amount': txamount, 'ts': txtime, 'ref': txref, 'payer_handle': handle})
    if found['certain']:
        return {'confidence': 'certain', 'transaction': found['certain'][0]}
    if len(found['high']) == 1:
        return {'confidence': 'high', 'transaction': found['high'][0]}
    if found['high'] or found['ambiguous']:  # several unknown payers could each be them: let the merchant pick
        return {'confidence': 'ambiguous', 'transaction': (found['high'] + found['ambiguous'])[0]}
    return None


def settle_debt(conn: sqlite3.Connection, debt_id: int, transaction: dict):
    """Atomic update; the null next_action_at is the stop-chasing signal."""
    with conn:
        row=conn.execute('SELECT status FROM debts WHERE id=?',(debt_id,)).fetchone()
        if not row or row[0] in ('settled','opted_out'):
            raise ValueError('Collection is already closed')
        used=conn.execute("SELECT 1 FROM contact_log WHERE outcome=?", ('verified:'+transaction['ref'],)).fetchone()
        if used:
            raise ValueError('Transaction has already been used')
        conn.execute("UPDATE debts SET status='settled', next_action_at=NULL WHERE id=?",(debt_id,))
        learned=None
        owner=conn.execute("SELECT c.id, c.payer_handle FROM debts d JOIN contacts c ON c.id=d.contact_id WHERE d.id=?",(debt_id,)).fetchone()
        if owner and not (owner[1] or '').strip() and (transaction.get('payer_handle') or '').strip():
            learned=transaction['payer_handle'].strip()  # the first payment teaches us who this customer pays as
            conn.execute("UPDATE contacts SET payer_handle=? WHERE id=?",(learned,owner[0]))
        conn.execute('INSERT INTO contact_log (debt_id, ts, channel, stage, transcript, outcome) VALUES (?, ?, ?, ?, ?, ?)',(debt_id,datetime.now().isoformat(timespec='seconds'),'sms',0,f"Verified ledger transaction {transaction['ref']} for ₹{transaction['amount']}. Stop chasing.",'verified:'+transaction['ref']))
    return learned
