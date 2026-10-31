from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from agent.routes import router as agent_router
from auth.routes import CURRENT_DB, get_identity, init_auth, merchant_db
from auth.routes import router as auth_router
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
app.mount("/ui", StaticFiles(directory=ROOT / "ui"), name="ui")  # after the routers: /ui/* is static, /api/ui/* is not
