from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from pydantic import BaseModel
import requests
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import json
import os
from datetime import datetime
from fastapi.responses import JSONResponse  # ← Add this
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # You can restrict this to http://localhost if needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Mount static and templates folders
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Murf API key
API_KEY = "ap2_46d2c473-54e1-4580-a711-4547d8757f96"

# Path to store audio history
HISTORY_FILE = "audio_history.json"

# Input model including voice
class TextInput(BaseModel):
    text: str
    voice: str  # ✅ dynamic voice selection

@app.post("/generate-audio")
def generate_audio(data: TextInput):
    url = "https://api.murf.ai/v1/speech/generate"
    headers = {
        "api-key": API_KEY,
        "Content-Type": "application/json"
    }

    payload = {
        "text": data.text,
        "voice_id": data.voice,
        "format": "mp3"
    }

    response = requests.post(url, headers=headers, json=payload)

    if response.status_code == 200:
        audio_url = response.json()["audioFile"]
        entry = {
            "text": data.text,
            "voice": data.voice,
            "audio_url": audio_url,
            "timestamp": datetime.now().isoformat()
        }

        # Append to audio history
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r") as f:
                history = json.load(f)
        else:
            history = []

        history.insert(0, entry)  # latest first

        with open(HISTORY_FILE, "w") as f:
            json.dump(history, f, indent=2)

        return {"message": "Audio generated", "data": response.json()}
    else:
        raise HTTPException(status_code=500, detail="TTS Generation failed")

@app.post("/upload-audio")
async def upload_audio(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        filename = f"recorded_{datetime.now().strftime('%Y%m%d%H%M%S')}.webm"
        save_path = os.path.join("static", filename)

        with open(save_path, "wb") as f:
            f.write(contents)

        return JSONResponse(content={"success": True, "message": "File uploaded", "filename": filename})

    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

@app.get("/", response_class=HTMLResponse)
@app.head("/")
async def home(request: Request):
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            history = json.load(f)
    else:
        history = []

    return templates.TemplateResponse("index.html", {
        "request": request,
        "history": history
    }) 
