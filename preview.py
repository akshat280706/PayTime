"""Standalone FastAPI demo app. Team should mount the routers in their own app.py instead."""
from pathlib import Path
import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
ROOT=Path(__file__).resolve().parent
os.environ.setdefault('PAYTIME_DB',str(ROOT/'state.db'))
from auth.routes import router as auth_router, get_identity, merchant_db, CURRENT_DB, init_auth
from fastapi.responses import JSONResponse
from ui.routes import router as ui_router
from verify.routes import router as verify_router
app=FastAPI(title='PayTime merchant portal')
init_auth()
app.include_router(auth_router)
@app.middleware('http')
async def merchant_scope(request, call_next):
    if request.url.path.startswith(('/api/ui/','/api/verify/')):
        identity=get_identity(request)
        if not identity:return JSONResponse({'detail':'Please sign in'},status_code=401)
        token=CURRENT_DB.set(merchant_db(identity['id'],bool(identity['demo'])))
        try:return await call_next(request)
        finally:CURRENT_DB.reset(token)
    return await call_next(request)
app.include_router(ui_router)
app.include_router(verify_router)
app.mount('/ui',StaticFiles(directory=ROOT/'ui'),name='ui')
@app.get('/')
def root():return RedirectResponse('/ui/index.html')
