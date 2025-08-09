from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import assemblyai as aai
import requests
import os
import json
from datetime import datetime

# Load environment variables from .env
load_dotenv()

app = FastAPI()

# Allow frontend to call APIs (restrict origin in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve your static assets and templates as before
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# API keys from environment
MURF_API_KEY = os.getenv("MURF_API_KEY")
ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY")

if not MURF_API_KEY:
    raise RuntimeError("MURF_API_KEY not set in environment")
if not ASSEMBLYAI_API_KEY:
    raise RuntimeError("ASSEMBLYAI_API_KEY not set in environment")

# Initialize AssemblyAI SDK (transcriber supports binary input)
aai.settings.api_key = ASSEMBLYAI_API_KEY
transcriber = aai.Transcriber()

# (Optional) Remove history usage for privacy — we won't read or write history file.
HISTORY_FILE = None


# ---------- Models ----------
class TextInput(BaseModel):
    text: str
    voice: str


# ---------- Routes ----------
@app.get("/", response_class=HTMLResponse)
@app.head("/")
async def home(request: Request):
    # Render UI template; we no longer send any shared history to the template
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/generate-audio")
def generate_audio(data: TextInput):
    """
    Generate audio using Murf TTS.
    Returns: {"message": "...", "data": <murf-response-json>}
    Keeps same shape as before so existing frontend code works.
    """
    url = "https://api.murf.ai/v1/speech/generate"
    headers = {
        "api-key": MURF_API_KEY,
        "Content-Type": "application/json"
    }

    payload = {
        "text": data.text,
        "voice_id": data.voice,
        "format": "mp3"
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
    except requests.RequestException as e:
        # return a helpful error message for frontend
        raise HTTPException(status_code=500, detail=f"Murf TTS request failed: {str(e)}")

    # Return Murf response JSON inside a small wrapper (keeps frontend unchanged)
    return {"message": "Audio generated", "data": resp.json()}


@app.post("/upload-audio")
async def upload_audio(file: UploadFile = File(...)):
    """
    Keep this endpoint for compatibility if frontend calls it,
    but DO NOT save the audio permanently. We simply accept it and return success.
    """
    try:
        contents = await file.read()  # read into memory
        # Optionally check file size or content-type for safety here
        size = len(contents)
        return JSONResponse(content={
            "success": True,
            "message": "File received (not saved)",
            "filename": getattr(file, "filename", None),
            "size": size
        })
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})


@app.post("/transcribe/file")
async def transcribe_file(file: UploadFile = File(...)):
    """
    Transcribe uploaded audio bytes in-memory using AssemblyAI.
    Returns: {"transcript": "..."}
    """
    try:
        audio_bytes = await file.read()  # binary in memory

        # Use AssemblyAI SDK transcriber that accepts binary data
        # The Transcriber.transcribe method supports passing bytes directly.
        transcript_obj = transcriber.transcribe(audio_bytes)

        # transcript_obj may have .text or .segments depending on SDK version
        text = getattr(transcript_obj, "text", None) or transcript_obj.get("text") if isinstance(transcript_obj, dict) else None

        if not text:
            # Last resort: try string conversion
            text = str(transcript_obj)

        return JSONResponse(content={"transcript": text})
    except Exception as e:
        # Log error to console (visible in server logs) and return JSON error for frontend
        print("Transcription error:", str(e))
        return JSONResponse(status_code=500, content={"error": str(e)})
