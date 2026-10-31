"""Read-only merchant dashboard + merchant-authorized actions.
Mount in shared app.py with app.include_router(ui_router).
"""
import os
import re
import sqlite3
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router=APIRouter(prefix='/api/ui',tags=['merchant UI'])
from auth.routes import CURRENT_DB


def connect():
    db=sqlite3.connect(CURRENT_DB.get(),timeout=10)
    db.row_factory=sqlite3.Row
    return db


@router.get('/dashboard')
def dashboard():
    with connect() as db:
        contacts=[dict(row) for row in db.execute('SELECT * FROM contacts ORDER BY id')]
        debts=[dict(row) for row in db.execute('SELECT * FROM debts ORDER BY CASE WHEN status="settled" THEN 1 ELSE 0 END, id')]
        logs=[dict(row) for row in db.execute('SELECT * FROM contact_log ORDER BY ts DESC LIMIT 100')]
        return {'contacts':contacts,'debts':debts,'logs':logs,'summary':{
            'outstanding':sum(d['amount'] for d in debts if d['status'] not in ('settled','opted_out')),
            'recovered':sum(d['amount'] for d in debts if d['status']=='settled')}}


@router.post('/debts/{debt_id}/approve-escalation')
def approve_escalation(debt_id:int):
    with connect() as db:
        d=db.execute('SELECT stage,status FROM debts WHERE id=?',(debt_id,)).fetchone()
        if not d: raise HTTPException(404,'Debt not found')
        if d['status']!='open' or d['stage']!=1:
            raise HTTPException(409,'Only active firm-stage debts can be approved for final escalation.')
        with db:
            db.execute('UPDATE debts SET stage=2 WHERE id=?',(debt_id,))
            db.execute('INSERT INTO contact_log (debt_id,ts,channel,stage,transcript,outcome) VALUES (?,?,?,?,?,?)',
                       (debt_id,datetime.now().isoformat(timespec='seconds'),'sms',2,'Merchant explicitly approved final stage. Use firm but respectful non-threatening language.','escalation_approved'))
        return {'approved':True,'debt_id':debt_id,'stage':2}


class Intake(BaseModel):
    text:str=''
    contact_id:int|None=None
    amount:float|None=None


@router.post('/intake')
def intake(request:Intake):
    """Hackathon fallback intake. Aryan can replace it with his natural-language parser."""
    with connect() as db:
        contacts=[dict(c) for c in db.execute('SELECT * FROM contacts')]
        c=next((c for c in contacts if c['id']==request.contact_id),None) if request.contact_id else None
        if c is None:
            # Prefer whole token matches to avoid matching 'Ram' inside another name.
            c=next((c for c in contacts if c['name'].lower() in request.text.lower()),None)
        if not c: raise HTTPException(422,'Customer not recognized. Please choose a customer from the dropdown.')
        amount=request.amount
        if amount is None:
            match=re.search(r'(?:₹|rs\.?\s*)(\d+(?:\.\d+)?)',request.text,re.I)
            if not match: match=re.search(r'\b(\d+(?:\.\d+)?)\b',request.text)
            if match: amount=float(match.group(1))
        if not amount or not (0<amount<=10000000): raise HTTPException(422,'Enter a valid amount.')
        existing=db.execute("SELECT id FROM debts WHERE contact_id=? AND ABS(amount-?)<0.01 AND status IN ('open','promised')",(c['id'],amount)).fetchone()
        if existing: return {'debt_id':existing['id'],'message':f"Already tracking {c['name']} for ₹{amount:g}."}
        now=datetime.now()
        with db:
            cursor=db.execute('INSERT INTO debts (contact_id,amount,created_at,due_date,stage,status,next_action_at) VALUES (?,?,?,?,?,?,?)',
                              (c['id'],amount,now.isoformat(timespec='seconds'),now.date().isoformat(),0,'open',(now+timedelta(days=1)).isoformat(timespec='seconds')))
        return {'debt_id':cursor.lastrowid,'message':f'Collection for {c["name"]} created.'}

class NewContact(BaseModel):
    name:str
    phone:str=''
    language:str='hi'

@router.post('/contacts')
def add_contact(payload:NewContact):
    if not payload.name.strip():raise HTTPException(422,'Customer name is required')
    if payload.language not in ('hi','en'):raise HTTPException(422,'Unsupported language')
    with connect() as db:
        with db:
            cur=db.execute('INSERT INTO contacts(name,phone,language) VALUES (?,?,?)',(payload.name.strip()[:90],payload.phone.strip()[:30],payload.language))
    return {'id':cur.lastrowid,'name':payload.name.strip()}


# ---- Manage screen: plain data control for rehearsing (add/edit/delete, land a payment, reset the demo data)
STATUSES=('open','promised','settled','disputed','opted_out','escalated')

class NewDebt(BaseModel):
    contact_id:int
    amount:float
    days_overdue:int=0

class DebtEdit(BaseModel):
    amount:float|None=None
    status:str|None=None

class PaymentFor(BaseModel):
    debt_id:int

def _forget_calls(debt_ids):
    from agent import conversation  # in-memory call transcripts for debts that no longer exist or were reset
    for i in debt_ids: conversation.CALLS.pop(i,None);conversation.CALL_META.pop(i,None)

@router.post('/manage/debts')
def manage_add_debt(p:NewDebt):
    if not (0<p.amount<=10000000):raise HTTPException(422,'Enter a valid amount.')
    if not (0<=p.days_overdue<=3650):raise HTTPException(422,'Days overdue must be 0 to 3650.')
    now=datetime.now(); due=now-timedelta(days=p.days_overdue)
    with connect() as db:
        if not db.execute('SELECT 1 FROM contacts WHERE id=?',(p.contact_id,)).fetchone():raise HTTPException(404,'Customer not found')
        with db:
            cur=db.execute('INSERT INTO debts (contact_id,amount,created_at,due_date,stage,status,next_action_at) VALUES (?,?,?,?,0,"open",?)',
                           (p.contact_id,p.amount,(due-timedelta(days=7)).isoformat(timespec='seconds'),due.isoformat(timespec='seconds'),now.isoformat(timespec='seconds')))
    return {'debt_id':cur.lastrowid}

@router.patch('/manage/debts/{debt_id}')
def manage_edit_debt(debt_id:int,p:DebtEdit):
    if p.amount is not None and not (0<p.amount<=10000000):raise HTTPException(422,'Enter a valid amount.')
    if p.status is not None and p.status not in STATUSES:raise HTTPException(422,'Unknown status.')
    with connect() as db:
        if not db.execute('SELECT 1 FROM debts WHERE id=?',(debt_id,)).fetchone():raise HTTPException(404,'Debt not found')
        with db:
            if p.amount is not None:db.execute('UPDATE debts SET amount=? WHERE id=?',(p.amount,debt_id))
            if p.status is not None:db.execute('UPDATE debts SET status=? WHERE id=?',(p.status,debt_id))
    return {'debt_id':debt_id}

def _delete_debts(db,ids):
    for i in ids:
        db.execute('DELETE FROM contact_log WHERE debt_id=?',(i,))
        db.execute('DELETE FROM promises WHERE debt_id=?',(i,))
        db.execute('DELETE FROM debts WHERE id=?',(i,))
    _forget_calls(ids)

@router.delete('/manage/debts/{debt_id}')
def manage_delete_debt(debt_id:int):
    with connect() as db:
        if not db.execute('SELECT 1 FROM debts WHERE id=?',(debt_id,)).fetchone():raise HTTPException(404,'Debt not found')
        with db:_delete_debts(db,[debt_id])
    return {'deleted':debt_id}

@router.delete('/manage/contacts/{contact_id}')
def manage_delete_contact(contact_id:int):
    with connect() as db:
        if not db.execute('SELECT 1 FROM contacts WHERE id=?',(contact_id,)).fetchone():raise HTTPException(404,'Customer not found')
        with db:
            ids=[r['id'] for r in db.execute('SELECT id FROM debts WHERE contact_id=?',(contact_id,))]
            _delete_debts(db,ids)
            db.execute('DELETE FROM contacts WHERE id=?',(contact_id,))
    return {'deleted':contact_id,'debts_deleted':len(ids)}

@router.post('/manage/payment')
def manage_payment(p:PaymentFor):
    from agent.state import add_payment
    with connect() as db:
        try:return add_payment(db,p.debt_id)
        except LookupError:raise HTTPException(404,'Debt not found')

@router.post('/manage/reset')
def manage_reset():
    """Re-run seed.py. Only for the demo workspace, whose database is the shared state.db."""
    import subprocess,sys
    from pathlib import Path
    root=Path(__file__).resolve().parent.parent
    if CURRENT_DB.get()!=str(root/'state.db'):raise HTTPException(403,'Reset is only available in the demo workspace.')
    done=subprocess.run([sys.executable,'seed.py'],cwd=root,capture_output=True,text=True,timeout=60)
    if done.returncode:raise HTTPException(500,'Seed failed: '+done.stderr[-300:])
    from agent import conversation
    conversation.CALLS.clear();conversation.CALL_META.clear()
    return {'summary':done.stdout.strip()}
