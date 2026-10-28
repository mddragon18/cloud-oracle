"""Sample workload app (Module 1): three endpoints of different weight.

- GET /        light page           (locust weight 5)
- GET /compute CPU-heavy calculation (locust weight 1, burns --cpus-sized cores)
- GET /download large download       (locust weight 1, ~4 MB response)

Run: uvicorn main:app --host 0.0.0.0 --port 8000
"""
import time

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response

import collector

app = FastAPI(title="oracle-workload")


@app.middleware("http")
async def record_latency(request: Request, call_next):
    start = time.monotonic()
    response = await call_next(request)
    if not request.url.path.startswith(("/docs", "/openapi")):
        collector.RECORDER.record((time.monotonic() - start) * 1000)
    return response


@app.get("/", response_class=HTMLResponse)
def light_page():
    return "<html><body><h1>oracle-workload</h1><p>light page</p></body></html>"


@app.get("/compute")
def compute(n: int = 1_500_000):
    total = 0
    for i in range(n):
        total += i * i % 7
    return {"result": total, "iterations": n}


@app.get("/download")
def download(kb: int = 4096):
    body = b"oracle-payload-" * (kb * 1024 // 15 + 1)
    return Response(
        content=body[: kb * 1024],
        media_type="application/octet-stream",
        headers={"Content-Disposition": 'attachment; filename="payload.bin"'},
    )


@app.on_event("startup")
def startup():
    collector.start_collector()
