from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from dispatcher.agent import run_dispatcher_with_mock, run_dispatcher_for_single_task
import json, os

app = FastAPI()

# Allow the frontend to access this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/dispatch")
def execute_dispatcher(taskId: str = None):
    """Reads the JSON file, calculates the new schedule, and returns it to the UI."""
    try:
        if not taskId:
            return {"error": "taskId query parameter is required"}
        # Calls the function we built in agent.py which parses web/HERO_data.js
        result_json = run_dispatcher_with_mock(taskId)
        return json.loads(result_json)
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/dispatch_task")
async def execute_task_dispatcher(request: Request):
    try:
        body = await request.json()
        task_id = body.get("task_id")
        if not task_id:
            return {"error": "No task_id provided"}
            
        result_json = run_dispatcher_for_single_task(task_id)
        return json.loads(result_json)
    except Exception as e:
        return {"error": str(e)}
        
@app.post("/api/save")
async def save_data(request: Request):
    """Takes JSON body from the dashboard and overwrites local files."""
    try:
        new_data = await request.json()
        
        # Write to core JSON file
        with open("data/HERO_data.json", "w", encoding="utf-8") as f:
            json.dump(new_data, f, indent=2, ensure_ascii=False)
            
        # Write to JS wrapper file to keep offline mode synced
        with open("web/HERO_data.js", "w", encoding="utf-8") as f:
            f.write("window.HERO_DATA = " + json.dumps(new_data, ensure_ascii=False) + ";")
            
        return {"status": "success"}
    except Exception as e:
        return {"error": str(e)}

# Root redirect -> sends visitors to the dashboard
@app.get("/")
def root():
    return RedirectResponse(url="/dashboard/index.html")

# Serve frontend files (mounted AFTER API routes so /api/* takes priority)
app.mount("/dashboard", StaticFiles(directory="web", html=True), name="dashboard")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
