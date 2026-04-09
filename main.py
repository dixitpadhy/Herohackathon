import os
import json
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# Resolve paths absolutely to avoid Cloud Run path confusion
BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "data" / "HERO_data.json"
WEB_DIR = BASE_DIR / "web"
STATIC_JSON_JS_PATH = WEB_DIR / "HERO_data.js"

app = FastAPI()

# Allow frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from pydantic import BaseModel, Field, ConfigDict

# ---------------------------------------------------------
# AI Schemas (Matches your latest Agent.py)
# ---------------------------------------------------------
class ReassignedTask(BaseModel):
    model_config = ConfigDict(extra="allow")
    task_id: str
    new_technician_id: str = Field(description="The ID of the new tech, or 'unassigned' if none found")
    scheduled_time: str
    human_explanation: str = Field(description="A plain-english justification for why this move happened")
    is_rescheduled_to_tomorrow: bool = Field(description="True if dropping low-priority tasks off today's schedule")

class DispatchResult(BaseModel):
    model_config = ConfigDict(extra="allow")
    assignments: List[ReassignedTask]
    confidence_score_percent: int = Field(description="0-100 score of how confident AI is in this plan")
    needs_human_review: bool = Field(description="True if confidence is low, or high financial assets are affected")
    executive_summary: str = Field(description="One paragraph summarizing the overall strategy chosen")

# ---------------------------------------------------------
# Data Layer Logic
# ---------------------------------------------------------
def get_hero_data():
    """Reads the JSON data from the central file."""
    try:
        if not DATA_PATH.exists():
            print(f"Warning: Data file not found at {DATA_PATH}")
            return {}
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error reading HERO_data.json: {e}")
        return {}

def build_dispatcher_payload():
    """Converts HERO data into the format Gemini expects."""
    data = get_hero_data()
    system_data = data.get("system_data", {})
    custom = system_data.get("custom_data_layer", {})
    
    # 1. Technicians
    technicians = []
    tech_ext = {ext["user_id"]: ext for ext in custom.get("technicians_extension", {}).get("skills_schema", {}).get("mapping", [])}
    status_ext = {ext["user_id"]: ext for ext in custom.get("technicians_extension", {}).get("status_schema", {}).get("mapping", [])}
    zone_ext = {ext["user_id"]: ext for ext in custom.get("technicians_extension", {}).get("geographic_zone_schema", {}).get("mapping", [])}
    
    for partner in system_data.get("partners", []):
        uid = partner["user_id"]
        technicians.append({
            "id": str(uid),
            "name": partner.get("full_name", str(uid)),
            "status": status_ext.get(uid, {}).get("status", "active"),
            "skills": tech_ext.get(uid, {}).get("skills", []),
            "geographic_zone": zone_ext.get(uid, {}).get("current_zone", "Berlin")
        })
        
    # 2. Tasks
    tasks = []
    biz_map = {m["task_id"]: m.get("business_value") for m in custom.get("tasks_extension", {}).get("business_value_schema", {}).get("mapping", [])}
    flex_map = {m["task_id"]: m.get("is_flexible") for m in custom.get("tasks_extension", {}).get("is_flexible_schema", {}).get("mapping", [])}
    skills_map = {m["task_id"]: m.get("required_skills") for m in custom.get("tasks_extension", {}).get("required_skills_schema", {}).get("mapping", [])}
    
    for proj in system_data.get("projects", []):
        if "task" in proj:
            tid = proj["task"]["id"]
            tasks.append({
                "id": str(tid),
                "description": proj["task"].get("title", "Task"),
                "required_skills": skills_map.get(tid, []),
                "business_value": biz_map.get(tid, "LOW"),
                "is_flexible": flex_map.get(tid, True),
                "scheduled_time": proj["task"].get("due_date", "None"),
                "geographic_zone": proj.get("address", {}).get("city", "Berlin"),
                "currently_assigned_to": str(proj["task"].get("target_user_id", "null"))
            })
            
    return {
        "technicians": technicians,
        "uncompleted_tasks": tasks
    }

# ---------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------
@app.post("/api/dispatch_task")
async def dispatch_task(request: Request):
    try:
        body = await request.json()
        raw_task_id = str(body.get("task_id"))
        clean_task_id = raw_task_id.replace("TSK-", "")
        
        payload = build_dispatcher_payload()
        target_task = next((t for t in payload["uncompleted_tasks"] if t["id"] == clean_task_id), None)
        
        if not target_task:
            return {"error": f"Task {clean_task_id} not found"}
            
        payload["target_task_to_reassign"] = target_task
        payload["trigger_event"] = {"event_type": "manual_reassignment", "message": f"Immediate dispatch for Task {clean_task_id}"}
        
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return {"error": "GEMINI_API_KEY environment variable is not set"}

        client = genai.Client(api_key=api_key)
        
        system_prompt = """
        You are an expert dispatcher reporting to Emilio. 
        Reassign the target task based on skills, status, and zone.
        In 'human_explanation', give exactly two sentences:
        1. Warm greeting to Emilio and justification.
        2. Quick Risk Assessment.
        """
        
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[system_prompt, f"Context: {json.dumps(payload, indent=2)}"],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=DispatchResult,
                temperature=0.1
            )
        )
        return json.loads(response.text)
        
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/save")
async def save_data(request: Request):
    """Saves data from UI and mirrors it in web/HERO_data.js."""
    try:
        new_data = await request.json()
        DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(new_data, f, indent=2, ensure_ascii=False)
        with open(STATIC_JSON_JS_PATH, "w", encoding="utf-8") as f:
            f.write("window.HERO_DATA = " + json.dumps(new_data, ensure_ascii=False) + ";")
        return {"status": "success"}
    except Exception as e:
        return {"error": str(e)}

# Root redirect handles the base URL
@app.get("/")
def root():
    return RedirectResponse(url="/dashboard/index.html")

# Serve static frontend files
app.mount("/dashboard", StaticFiles(directory=str(WEB_DIR), html=True), name="dashboard")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
