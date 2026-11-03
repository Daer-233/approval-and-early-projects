from __future__ import annotations

import asyncio
import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .splitter import build_rules, split_payment_allowances

APP_DATA_DIR = Path(os.getenv("APP_DATA_DIR", Path(__file__).resolve().parents[1] / "data"))
UPLOAD_DIR = APP_DATA_DIR / "uploads"
OUTPUT_DIR = APP_DATA_DIR / "outputs"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="补贴付款拆分工作台 API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

tasks: dict[str, dict[str, Any]] = {}
task_refs: dict[str, asyncio.Task[Any]] = {}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def public_task(task: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in task.items() if key not in {"input_path", "output_root"}}


async def process_task(task_id: str, input_path: Path, output_root: Path) -> None:
    task = tasks[task_id]
    task["status"] = "running"
    task["started_at"] = utc_now()
    try:
        result = await asyncio.to_thread(split_payment_allowances, input_path, output_root)
        task["status"] = "completed"
        task["finished_at"] = utc_now()
        task["result"] = result
    except Exception as exc:  # noqa: BLE001 - expose friendly validation message to the UI
        task["status"] = "failed"
        task["finished_at"] = utc_now()
        task["error"] = str(exc)
    finally:
        input_path.unlink(missing_ok=True)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "allowance-workbench"}


@app.get("/api/rules")
async def rules() -> dict[str, Any]:
    return {
        "count": 19,
        "items": [
            {
                "payment_department": rule.payment_department,
                "company": rule.company,
                "scope": rule.scope,
                "filename_stem": rule.filename_stem,
            }
            for rule in build_rules("当月")
        ],
    }


@app.post("/api/tasks")
async def create_task(file: UploadFile = File(...)) -> dict[str, Any]:
    original_name = file.filename or "上传文件.xlsx"
    if not original_name.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="目前只支持可编辑、未加密的 .xlsx 文件。")
    task_id = uuid.uuid4().hex
    task_dir = OUTPUT_DIR / task_id
    input_path = UPLOAD_DIR / f"{task_id}.xlsx"
    try:
        with input_path.open("wb") as target:
            shutil.copyfileobj(file.file, target)
    except Exception as exc:  # noqa: BLE001
        input_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"文件保存失败：{exc}") from exc

    task = {
        "id": task_id,
        "status": "queued",
        "file_name": original_name,
        "created_at": utc_now(),
        "input_path": input_path,
        "output_root": task_dir,
    }
    tasks[task_id] = task
    task_refs[task_id] = asyncio.create_task(process_task(task_id, input_path, task_dir))
    return public_task(task)


@app.get("/api/tasks")
async def list_tasks() -> dict[str, Any]:
    items = sorted((public_task(item) for item in tasks.values()), key=lambda item: item["created_at"], reverse=True)
    return {"items": items[:20]}


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str) -> dict[str, Any]:
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在或服务已重启。")
    return public_task(task)


def task_file(task_id: str, key: str) -> tuple[Path, str]:
    task = tasks.get(task_id)
    if not task or task.get("status") != "completed":
        raise HTTPException(status_code=409, detail="任务尚未完成，暂时无法下载。")
    result = task.get("result", {})
    raw_path = result.get(key)
    if not raw_path:
        raise HTTPException(status_code=404, detail="结果文件不存在。")
    path = Path(raw_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="结果文件已被移除。")
    return path, path.name


@app.get("/api/tasks/{task_id}/download/summary")
async def download_summary(task_id: str) -> FileResponse:
    path, filename = task_file(task_id, "summary")
    return FileResponse(path, filename=filename, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.get("/api/tasks/{task_id}/download/zip")
async def download_zip(task_id: str) -> FileResponse:
    path, filename = task_file(task_id, "zip")
    return FileResponse(path, filename=filename, media_type="application/zip")


@app.get("/api/tasks/{task_id}/download/department/{index}")
async def download_department(task_id: str, index: int) -> FileResponse:
    task = tasks.get(task_id)
    if not task or task.get("status") != "completed":
        raise HTTPException(status_code=409, detail="任务尚未完成，暂时无法下载。")
    departments = task.get("result", {}).get("departments", [])
    if index < 0 or index >= len(departments):
        raise HTTPException(status_code=404, detail="付款部门不存在。")
    detail_dir = Path(task["result"]["detail_folder"])
    path = detail_dir / task["result"]["departments"][index]["file_name"]
    if not path.is_file():
        # The child files are inside the known result directory; this keeps the API strict.
        raise HTTPException(status_code=404, detail="子表文件不存在。")
    return FileResponse(path, filename=path.name, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.on_event("shutdown")
async def shutdown_event() -> None:
    for ref in task_refs.values():
        if not ref.done():
            ref.cancel()


# Optional local serving of a built frontend. In Nginx deployment Nginx serves it instead.
frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
