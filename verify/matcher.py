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
        conn.execute('INSERT INTO contact_log (debt_id, ts, channel, stage, transcript, outcome) VALUES (?, ?, ?, ?, ?, ?)',(debt_id,datetime.now().isoformat(timespec='seconds'),'sms',0,f"Verified ledger transaction {transaction['ref']} for ₹{transaction['amount']}. Stop chasing.",'verified:'+transaction['ref']))
