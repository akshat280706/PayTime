from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from agent.routes import router as agent_router
from voice.routes import router as voice_router
from verify.routes import router as verify_router

app = FastAPI(title="PayTime")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/")
def index():
    return FileResponse("ui/index.html")


app.include_router(agent_router)
app.include_router(voice_router)
app.include_router(verify_router)
