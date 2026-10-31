import os
from contextlib import closing
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent.routes import router as agent_router
from agent.state import add_payment
from auth.routes import CURRENT_DB, get_identity, init_auth, merchant_db
from auth.routes import router as auth_router
from db import get_db
from ui.routes import router as ui_router
from voice.routes import router as voice_router
from verify.routes import router as verify_router

ROOT = Path(__file__).resolve().parent
app = FastAPI(title="PayTime")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
init_auth()


@app.middleware("http")
async def merchant_scope(request: Request, call_next):
    """The merchant UI and verification routes need a session and run against that merchant's database."""
    if request.url.path.startswith(("/api/ui/", "/api/verify/")):
        identity = get_identity(request)
        if not identity:
            return JSONResponse({"detail": "Please sign in"}, status_code=401)
        token = CURRENT_DB.set(merchant_db(identity["id"], bool(identity["demo"])))
        try:
            return await call_next(request)
        finally:
            CURRENT_DB.reset(token)
    return await call_next(request)


@app.get("/")
def index():
    return FileResponse("ui/index.html")


app.include_router(auth_router)
app.include_router(ui_router)
app.include_router(agent_router)
app.include_router(voice_router)
app.include_router(verify_router)
class DemoPayment(BaseModel):
    debt_id: int


@app.post("/api/demo/payment", include_in_schema=False)
def demo_payment(body: DemoPayment):
    """Stands in for Paytm's payment webhook: drops a successful payment for this debt into the feed.
    No auth on purpose (reachable from a phone on the LAN); remove before anything real uses this app."""
    with closing(get_db()) as db:
        try:
            return add_payment(db, body.debt_id)
        except LookupError:
            raise HTTPException(404, "Debt not found")


app.mount("/ui", StaticFiles(directory=ROOT / "ui"), name="ui")  # after the routers: /ui/* is static, /api/ui/* is not


if __name__ == "__main__":  # python app.py -> reachable from other machines on the LAN
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
