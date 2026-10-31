"""Mount router in the shared app.py: app.include_router(verify_router)."""
import os
import sqlite3
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from .ocr import read_receipt
from .matcher import match_feed_transaction, match_transaction, settle_debt

router=APIRouter(prefix='/api/verify',tags=['verification'])
from auth.routes import CURRENT_DB


def connect():
    conn=sqlite3.connect(CURRENT_DB.get(),timeout=10)
    conn.row_factory=sqlite3.Row
    return conn


@router.get('/transactions')
def transactions():
    with connect() as db:
        return {'transactions':[dict(x) for x in db.execute('SELECT * FROM transactions ORDER BY ts DESC LIMIT 30')]}


@router.post('/screenshot')
async def verify_screenshot(debt_id: int=Form(...),file: UploadFile=File(...)):
    if file.content_type not in ('image/png','image/jpeg','image/webp'):
        raise HTTPException(400,'Upload a PNG, JPG or WEBP image')
    body=await file.read(8*1024*1024+1)
    if len(body)>8*1024*1024:
        raise HTTPException(400,'Image size exceeds 8 MB')
    try:
        claim=read_receipt(body,file.content_type)
    except Exception as ex:
        raise HTTPException(422,f'Could not read screenshot: {ex}')
    with connect() as db:
        debt=db.execute('SELECT status FROM debts WHERE id=?',(debt_id,)).fetchone()
        if not debt: raise HTTPException(404,'Collection not found')
        if debt['status'] in ('settled','opted_out'): raise HTTPException(409,'Collection already closed')
        txn=match_transaction(db,debt_id=debt_id,**claim)
        if not txn:
            return {'verified':False,'message':'Payment unverified: no matching successful ledger transaction. Do not accuse the customer; recheck later.','claim':claim}
        try: settle_debt(db,debt_id,txn)
        except ValueError as ex: raise HTTPException(409,str(ex))
        return {'verified':True,'amount':txn['amount'],'transaction_ref':txn['ref'],'debt_id':debt_id,'stopped':True}


@router.post('/check/{debt_id}')
def check_feed(debt_id: int):
    """Feed-only verification, no screenshot: used when the agent reports trigger_verification."""
    with connect() as db:
        debt=db.execute('SELECT status FROM debts WHERE id=?',(debt_id,)).fetchone()
        if not debt: raise HTTPException(404,'Collection not found')
        if debt['status'] in ('settled','opted_out'): raise HTTPException(409,'Collection already closed')
        match=match_feed_transaction(db,debt_id=debt_id)
        if not match:
            return {'verified':False,'message':'Payment unverified: no matching successful ledger transaction yet. Do not accuse the customer; recheck later.'}
        txn=match['transaction']
        if match['confidence']=='ambiguous':
            return {'verified':False,'needs_review':True,'confidence':'ambiguous','candidate':txn,
                    'message':'A transaction for this amount exists but cannot be tied to this customer. Merchant review needed; not settled.'}
        try: learned=settle_debt(db,debt_id,txn)
        except ValueError as ex: raise HTTPException(409,str(ex))
        return {'verified':True,'amount':txn['amount'],'transaction_ref':txn['ref'],'debt_id':debt_id,'stopped':True,
                'confidence':match['confidence'],'payer_handle_learned':learned}
