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
    if payload.language not in ('hi','mr','ta','en'):raise HTTPException(422,'Unsupported language')
    with connect() as db:
        with db:
            cur=db.execute('INSERT INTO contacts(name,phone,language) VALUES (?,?,?)',(payload.name.strip()[:90],payload.phone.strip()[:30],payload.language))
    return {'id':cur.lastrowid,'name':payload.name.strip()}
