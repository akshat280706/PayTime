"""Hackathon merchant workspaces: server-side sessions and per-merchant SQLite files.
This is a standalone preview integration. Team backend can mount the router/middleware.
"""
import hashlib, hmac, os, secrets, sqlite3, time
from pathlib import Path
from contextvars import ContextVar
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel
ROOT=Path(__file__).resolve().parent.parent
AUTH_DB=ROOT/'merchant_auth.db'
CURRENT_DB=ContextVar('merchant_db',default=str(ROOT/'state.db'))
router=APIRouter(prefix='/api/auth',tags=['merchant authentication'])

def init_auth():
    with sqlite3.connect(AUTH_DB) as db:
        db.execute('CREATE TABLE IF NOT EXISTS merchants (id INTEGER PRIMARY KEY, owner TEXT NOT NULL, store TEXT NOT NULL, email TEXT UNIQUE NOT NULL, salt TEXT NOT NULL, password_hash TEXT NOT NULL, demo INTEGER DEFAULT 0)')
        db.execute('CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, merchant_id INTEGER NOT NULL, expires INTEGER NOT NULL)')
        if not db.execute('SELECT id FROM merchants WHERE demo=1').fetchone():
            salt=secrets.token_hex(16)
            ph=hashlib.scrypt(b'demo-only-not-a-login',salt=bytes.fromhex(salt),n=2**14,r=8,p=1).hex()
            db.execute('INSERT INTO merchants (owner,store,email,salt,password_hash,demo) VALUES (?,?,?,?,?,1)',('Demo merchant','Sharma General Store','demo@paytime.local',salt,ph))

def merchant_db(mid:int,demo:bool=False)->str:
    if demo: return str(ROOT/'state.db')
    path=ROOT/'merchant_data'/f'merchant_{mid}.db'
    path.parent.mkdir(exist_ok=True)
    if not path.exists():
        with sqlite3.connect(path) as db:
            db.executescript((ROOT/'schema.sql').read_text())
    return str(path)

def get_identity(request:Request):
    token=request.cookies.get('paytime_session')
    if not token:return None
    digest=hashlib.sha256(token.encode()).hexdigest()
    with sqlite3.connect(AUTH_DB) as db:
        db.row_factory=sqlite3.Row
        row=db.execute('SELECT m.id,m.owner,m.store,m.email,m.demo FROM merchants m JOIN sessions s ON s.merchant_id=m.id WHERE s.token_hash=? AND s.expires>?',(digest,int(time.time()))).fetchone()
    return dict(row) if row else None

def set_session(response:Response,mid:int):
    token=secrets.token_urlsafe(32)
    with sqlite3.connect(AUTH_DB) as db:
        db.execute('INSERT INTO sessions VALUES (?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),mid,int(time.time())+7*86400))
    response.set_cookie('paytime_session',token,max_age=7*86400,httponly=True,samesite='lax',secure=os.getenv('PAYTIME_HTTPS')=='1',path='/')

class Credentials(BaseModel):
    email:str
    password:str
    name:str|None=None
    store:str|None=None

@router.post('/signup')
def signup(payload:Credentials,response:Response):
    email=payload.email.strip().lower()
    name=(payload.name or '').strip();store=(payload.store or '').strip()
    if not (name and store and '@' in email and len(payload.password)>=8): raise HTTPException(422,'Enter a name, business, valid email and password of at least 8 characters.')
    salt=secrets.token_hex(16)
    ph=hashlib.scrypt(payload.password.encode(),salt=bytes.fromhex(salt),n=2**14,r=8,p=1).hex()
    try:
        with sqlite3.connect(AUTH_DB) as db:
            cur=db.execute('INSERT INTO merchants (owner,store,email,salt,password_hash) VALUES (?,?,?,?,?)',(name[:100],store[:100],email[:254],salt,ph))
            mid=cur.lastrowid
    except sqlite3.IntegrityError:raise HTTPException(409,'An account already exists for this email.')
    merchant_db(mid)
    set_session(response,mid)
    return {'id':mid,'owner':name,'store':store,'email':email}

@router.post('/login')
def login(payload:Credentials,response:Response):
    with sqlite3.connect(AUTH_DB) as db:
        db.row_factory=sqlite3.Row
        m=db.execute('SELECT * FROM merchants WHERE email=? AND demo=0',(payload.email.strip().lower(),)).fetchone()
    if not m:raise HTTPException(401,'Incorrect email or password.')
    ph=hashlib.scrypt(payload.password.encode(),salt=bytes.fromhex(m['salt']),n=2**14,r=8,p=1).hex()
    if not hmac.compare_digest(ph,m['password_hash']):raise HTTPException(401,'Incorrect email or password.')
    set_session(response,m['id'])
    return {'id':m['id'],'owner':m['owner'],'store':m['store'],'email':m['email']}

@router.post('/demo')
def demo(response:Response):
    with sqlite3.connect(AUTH_DB) as db:mid=db.execute('SELECT id FROM merchants WHERE demo=1').fetchone()[0]
    set_session(response,mid)
    return {'id':mid,'owner':'Demo merchant','store':'Sharma General Store','email':'demo@paytime.local','demo':True}

@router.get('/me')
def me(request:Request):
    m=get_identity(request)
    if not m:raise HTTPException(401,'Sign in to continue.')
    return m

@router.post('/logout')
def logout(request:Request,response:Response):
    token=request.cookies.get('paytime_session')
    if token:
        with sqlite3.connect(AUTH_DB) as db:db.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(token.encode()).hexdigest(),))
    response.delete_cookie('paytime_session',path='/')
    return {'ok':True}
