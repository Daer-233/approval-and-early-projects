from __future__ import annotations

import asyncio
import gc
import io
import shutil
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .db import Database
from .dingtalk import (
    DingTalkClient,
    DingTalkError,
    build_display_fields,
    forecast_signature,
    form_values_from_schema,
    normalize_forecast,
    validate_node_actioners,
)
from .office_bridge import AuthorizedOfficeImportError, export_authorized_workbook
from .splitter import analyze_payment_allowances, build_rules, generate_selected_payment_files
from .spreadsheet_import import SpreadsheetImportError, normalize_workbook, workbook_extension

ROOT_DIR = Path(__file__).resolve().parents[1]
APP_DATA_DIR = Path(__import__("os").getenv("APP_DATA_DIR", ROOT_DIR / "data"))
UPLOAD_DIR, OUTPUT_DIR = APP_DATA_DIR / "uploads", APP_DATA_DIR / "outputs"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
db = Database(APP_DATA_DIR / "workflow.db")
dingtalk = DingTalkClient()

app = FastAPI(title="企业业务平台 API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def unlink_quietly(path: Path) -> None:
    for delay in (0, 0.05, 0.2):
        if delay:
            time.sleep(delay)
        try:
            path.unlink(missing_ok=True)
            return
        except PermissionError:
            gc.collect()
        except OSError:
            return


def public_task(task: dict[str, Any]) -> dict[str, Any]:
    item = {key: value for key, value in task.items() if key not in {"source_path", "output_root"}}
    if isinstance(item.get("result"), dict):
        result = dict(item["result"])
        result["departments"] = [{key: value for key, value in department.items() if key != "file_path"} for department in result.get("departments", [])]
        for key in ("summary", "zip", "detail_folder", "output_directory"):
            result.pop(key, None)
        item["result"] = result
    item["approval_attempts"] = db.approval_attempts(task["id"])
    return item


def get_task_or_404(task_id: str) -> dict[str, Any]:
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在。")
    return task


class GroupChoice(BaseModel):
    group_id: str
    selected: bool = True
    payment_department: str = ""
    remember_mapping: bool = True
    # Retained only to load task JSON written by the old fixed-role UI.
    approvers: dict[str, dict[str, str]] = Field(default_factory=dict)


class TaskChoices(BaseModel):
    groups: list[GroupChoice]


class CompanyProfile(BaseModel):
    company: str
    payment_entity: str
    supplier_name: str
    bank_account: str
    bank_name: str


class ConfirmSubmit(BaseModel):
    confirm: bool = False


class SelectedUser(BaseModel):
    user_id: str
    name: str = ""


class WorkflowActioners(BaseModel):
    groups: dict[str, dict[str, list[SelectedUser]]] = Field(default_factory=dict)


class SelectedDownloads(BaseModel):
    indices: list[int] = Field(default_factory=list)


async def save_and_analyze(
    file: UploadFile,
    upload_path: Path,
    input_path: Path,
    original_name: str,
    import_mode: str = "标准上传",
) -> dict[str, Any]:
    error_detail: str | None = None
    try:
        with upload_path.open("wb") as target:
            shutil.copyfileobj(file.file, target)
        await asyncio.to_thread(normalize_workbook, upload_path, input_path)
        analysis = await asyncio.to_thread(analyze_payment_allowances, input_path, db.mapping_dict())
    except Exception as exc:
        error_detail = str(exc)
    if error_detail is not None:
        unlink_quietly(upload_path)
        unlink_quietly(input_path)
        raise HTTPException(status_code=400, detail=error_detail)
    if upload_path != input_path:
        unlink_quietly(upload_path)
    task_id = input_path.stem.split("-")[0]
    task = {
        "id": task_id, "status": "review", "file_name": original_name, "created_at": utc_now(), "updated_at": utc_now(),
        "source_path": str(input_path), "output_root": str(OUTPUT_DIR / task_id), "error": None,
        "analysis": analysis, "choices": [], "result": None, "previews": [], "workflow_forecasts": {}, "workflow_actioners": {}, "import_mode": import_mode,
    }
    db.save_task(task)
    return public_task(task)


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "service": "allowance-workbench", "database": "sqlite", "dingtalk_configured": not dingtalk.config.missing}


@app.get("/api/rules")
async def rules() -> dict[str, Any]:
    items = [{"payment_department": rule.payment_department, "company": rule.company, "scope": rule.scope, "filename_stem": rule.filename_stem} for rule in build_rules("当月")]
    return {"count": len(items), "mode": "dynamic", "description": "按实际数据动态分组，以下规则仅用于特殊合并。", "items": items}


@app.post("/api/tasks")
async def create_task(file: UploadFile = File(...)) -> dict[str, Any]:
    original_name = file.filename or "上传文件.xlsx"
    try:
        suffix = workbook_extension(original_name)
    except SpreadsheetImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    task_id = uuid.uuid4().hex
    upload_path = UPLOAD_DIR / f"{task_id}{suffix}"
    input_path = UPLOAD_DIR / f"{task_id}.xlsx"
    import_mode = "标准上传" if suffix == ".xlsx" else f"{suffix[1:].upper()} 转换导入"
    return await save_and_analyze(file, upload_path, input_path, original_name, import_mode)


@app.post("/api/tasks/authorized-office")
async def create_authorized_office_task(file: UploadFile = File(...), password: str = Form("")) -> dict[str, Any]:
    original_name = file.filename or "上传文件.xlsx"
    if not original_name.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="本机 WPS / Microsoft Excel 授权导入仅支持 .xlsx；.ods 和 .numbers 请使用标准上传。")
    task_id = uuid.uuid4().hex
    source_path, input_path = UPLOAD_DIR / f"{task_id}-office-source.xlsx", UPLOAD_DIR / f"{task_id}.xlsx"
    try:
        with source_path.open("wb") as target:
            shutil.copyfileobj(file.file, target)
        await asyncio.to_thread(export_authorized_workbook, source_path, input_path, password)
    except AuthorizedOfficeImportError as exc:
        input_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        source_path.unlink(missing_ok=True)
    # save_and_analyze expects an UploadFile, so analyze the authorised copy directly.
    try:
        analysis = await asyncio.to_thread(analyze_payment_allowances, input_path, db.mapping_dict())
    except Exception as exc:
        input_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    task = {"id": task_id, "status": "review", "file_name": original_name, "created_at": utc_now(), "updated_at": utc_now(),
            "source_path": str(input_path), "output_root": str(OUTPUT_DIR / task_id), "error": None, "analysis": analysis,
            "choices": [], "result": None, "previews": [], "workflow_forecasts": {}, "workflow_actioners": {}, "import_mode": "本机 WPS / Microsoft Excel 授权导入"}
    db.save_task(task)
    return public_task(task)


@app.get("/api/tasks")
async def list_tasks() -> dict[str, Any]:
    return {"items": [public_task(task) for task in db.list_tasks(30)]}


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str) -> dict[str, Any]:
    return public_task(get_task_or_404(task_id))


@app.put("/api/tasks/{task_id}/groups")
async def update_groups(task_id: str, body: TaskChoices) -> dict[str, Any]:
    task = get_task_or_404(task_id)
    analysis_groups = {group["id"]: group for group in task["analysis"]["groups"]}
    choices = []
    for choice_model in body.groups:
        choice = choice_model.model_dump()
        source = analysis_groups.get(choice["group_id"])
        if not source:
            raise HTTPException(status_code=400, detail=f"分组不存在：{choice['group_id']}")
        if choice["selected"] and not choice["payment_department"].strip():
            raise HTTPException(status_code=400, detail=f"{source['company']} / {source['suggested_department']} 尚未指定付款部门。")
        choices.append(choice)
        if choice["remember_mapping"] and not source["known_rule"] and choice["payment_department"].strip():
            for source_department in source["source_departments"]:
                db.save_mapping(source["company"], source_department, choice["payment_department"].strip(), utc_now())
    task.update({"choices": choices, "status": "review", "result": None, "previews": [], "workflow_forecasts": {}, "workflow_actioners": {}, "updated_at": utc_now(), "error": None})
    db.save_task(task)
    return public_task(task)


@app.post("/api/tasks/{task_id}/prepare")
async def prepare_task(task_id: str) -> dict[str, Any]:
    task = get_task_or_404(task_id)
    if not task.get("choices"):
        raise HTTPException(status_code=409, detail="请先确认本次付款部门和未知部门归属。")
    try:
        result = await asyncio.to_thread(generate_selected_payment_files, Path(task["source_path"]), Path(task["output_root"]), task["choices"], db.mapping_dict())
        task.update({"result": result, "status": "prepared", "previews": [], "workflow_forecasts": {}, "workflow_actioners": {}, "updated_at": utc_now(), "error": None})
        db.save_task(task)
    except Exception as exc:
        task.update({"status": "failed", "error": str(exc), "updated_at": utc_now()})
        db.save_task(task)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return public_task(task)


@app.get("/api/company-profiles")
async def company_profiles() -> dict[str, Any]:
    return {"items": db.list_profiles()}


@app.put("/api/company-profiles/{company}")
async def update_company_profile(company: str, profile: CompanyProfile) -> dict[str, Any]:
    if company != profile.company:
        raise HTTPException(status_code=400, detail="公司主体与路径不一致。")
    item = profile.model_dump()
    item["updated_at"] = utc_now()
    db.save_profile(item)
    return item


@app.get("/api/department-mappings")
async def department_mappings() -> dict[str, Any]:
    return {"items": db.list_mappings()}


@app.get("/api/dingtalk/preflight")
async def dingtalk_preflight(remote: bool = Query(False)) -> dict[str, Any]:
    return await asyncio.to_thread(dingtalk.preflight, remote)


@app.get("/api/dingtalk/users")
async def dingtalk_users(keyword: str = Query("", max_length=60)) -> dict[str, Any]:
    if dingtalk.config.missing:
        return {"items": [], "configured": False}
    try:
        return {"items": await asyncio.to_thread(dingtalk.list_users, keyword), "configured": True}
    except DingTalkError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def _profile_errors(profile: dict[str, Any]) -> list[str]:
    missing = [label for key, label in (("payment_entity", "付款主体"), ("supplier_name", "供应商名称"), ("bank_account", "银行账号"), ("bank_name", "开户银行")) if not profile.get(key)]
    return ["公司付款资料缺少：" + "、".join(missing)] if missing else []


def _node_actioners(task: dict[str, Any], group_id: str) -> dict[str, list[dict[str, str]]]:
    raw = (task.get("workflow_actioners") or {}).get(group_id) or {}
    return {
        str(actor_key): [
            {"user_id": str(user.get("user_id") or ""), "name": str(user.get("name") or "")}
            for user in users if isinstance(user, dict)
        ]
        for actor_key, users in raw.items() if isinstance(users, list)
    }


def preview_items(task: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    result = task.get("result") or {}
    items, all_valid = [], True
    for group in result.get("departments", []):
        profile = db.get_profile(group["company"]) or {"company": group["company"], "payment_entity": "", "supplier_name": "", "bank_account": "", "bank_name": ""}
        forecast = (task.get("workflow_forecasts") or {}).get(group["id"]) or {}
        nodes = forecast.get("nodes") or []
        actioners = _node_actioners(task, group["id"])
        errors = _profile_errors(profile)
        if forecast.get("error"):
            errors.append("流程预测失败：" + str(forecast["error"]))
        elif not forecast:
            errors.append("尚未检测钉钉审批流程。")
        else:
            errors.extend(validate_node_actioners(nodes, actioners))
        fields = build_display_fields(group, profile, result.get("month", "当月"), group["file_name"], dingtalk.config.originator_dept_id)
        valid = not errors
        all_valid = all_valid and valid
        items.append({"group_id": group["id"], "company": group["company"], "payment_department": group["payment_department"],
                      "count": group["count"], "amount": group["amount"], "attachment_name": group["file_name"], "nodes": nodes,
                      "node_actioners": actioners, "signature": forecast.get("signature", ""), "fields": fields, "valid": valid, "errors": errors})
    return items, all_valid


@app.post("/api/tasks/{task_id}/approvals/forecast")
async def approval_forecast(task_id: str) -> dict[str, Any]:
    task = get_task_or_404(task_id)
    if not task.get("result"):
        raise HTTPException(status_code=409, detail="请先生成选中部门的附件。")
    try:
        schema = await asyncio.to_thread(dingtalk.get_schema)
    except DingTalkError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    forecasts: dict[str, dict[str, Any]] = {}
    for group in task["result"].get("departments", []):
        profile = db.get_profile(group["company"]) or {}
        fields = build_display_fields(group, profile, task["result"].get("month", "当月"), group["file_name"], dingtalk.config.originator_dept_id)
        try:
            raw = await asyncio.to_thread(dingtalk.forecast, form_values_from_schema(schema, fields))
            normalized = normalize_forecast(raw)
            if not normalized["success"]:
                raise DingTalkError("钉钉未返回可用的流程预测结果")
            forecasts[group["id"]] = {
                **normalized,
                "name": f"{group['company']} · {group['payment_department']}",
                "signature": forecast_signature(normalized["nodes"]),
                "predicted_at": utc_now(),
                "error": None,
            }
        except Exception as exc:
            forecasts[group["id"]] = {
                "nodes": [],
                "name": f"{group['company']} · {group['payment_department']}",
                "signature": "",
                "predicted_at": utc_now(),
                "error": str(exc),
            }
    task.update({"workflow_forecasts": forecasts, "previews": [], "status": "prepared", "updated_at": utc_now()})
    db.save_task(task)
    return {"groups": [{"group_id": group_id, **forecast, "node_actioners": _node_actioners(task, group_id)} for group_id, forecast in forecasts.items()]}


@app.put("/api/tasks/{task_id}/approvals/actioners")
async def update_workflow_actioners(task_id: str, body: WorkflowActioners) -> dict[str, Any]:
    task = get_task_or_404(task_id)
    forecasts = task.get("workflow_forecasts") or {}
    cleaned: dict[str, dict[str, list[dict[str, str]]]] = {}
    for group_id, selections in body.groups.items():
        if group_id not in forecasts:
            raise HTTPException(status_code=400, detail=f"付款分组尚未完成流程检测：{group_id}")
        nodes = forecasts[group_id].get("nodes") or []
        values = {key: [user.model_dump() for user in users] for key, users in selections.items()}
        errors = validate_node_actioners(nodes, values)
        if errors:
            raise HTTPException(status_code=400, detail="；".join(errors))
        cleaned[group_id] = values
    task.update({"workflow_actioners": cleaned, "previews": [], "status": "prepared", "updated_at": utc_now()})
    db.save_task(task)
    return {"groups": cleaned}


@app.post("/api/tasks/{task_id}/approvals/preview")
async def approval_preview(task_id: str) -> dict[str, Any]:
    task = get_task_or_404(task_id)
    if not task.get("result"):
        raise HTTPException(status_code=409, detail="请先生成选中部门的附件。")
    items, valid = preview_items(task)
    task.update({"previews": items, "status": "previewed", "updated_at": utc_now()})
    db.save_task(task)
    return {"items": items, "valid": valid, "connection": dingtalk.public_config()}


async def submit_approvals(task: dict[str, Any], failed_only: bool) -> dict[str, Any]:
    if not dingtalk.config.live_submit_enabled:
        raise HTTPException(status_code=409, detail="正式提交开关未开启。请先使用测试审批模板完成联调。")
    preflight = await asyncio.to_thread(dingtalk.preflight, True)
    if not preflight.get("ok"):
        raise HTTPException(status_code=409, detail="钉钉预检未通过：" + "；".join(preflight.get("messages", [])))
    items, valid = preview_items(task)
    if not valid:
        raise HTTPException(status_code=409, detail="审批预览仍有未完成配置。")
    result_groups = {group["id"]: group for group in task["result"]["departments"]}
    task.update({"status": "submitting", "updated_at": utc_now()})
    db.save_task(task)
    schema = await asyncio.to_thread(dingtalk.get_schema)
    for item in items:
        existing = db.get_attempt(task["id"], item["group_id"])
        if existing and existing["status"] == "submitted":
            continue
        if failed_only and (not existing or existing["status"] != "failed"):
            continue
        group = result_groups[item["group_id"]]
        request_id = existing["request_id"] if existing else uuid.uuid4().hex
        attempt = {"task_id": task["id"], "group_id": item["group_id"], "status": "submitting", "instance_id": None,
                   "error": None, "request_id": request_id, "payload": {"department": item["payment_department"], "amount": item["amount"]}, "updated_at": utc_now()}
        db.save_attempt(attempt)
        try:
            attachment = await asyncio.to_thread(dingtalk.upload_approval_attachment, Path(group["file_path"]))
            form_values = form_values_from_schema(schema, item["fields"], attachment)
            forecast = normalize_forecast(await asyncio.to_thread(dingtalk.forecast, form_values))
            expected = (task.get("workflow_forecasts") or {}).get(item["group_id"], {}).get("signature", "")
            actual = forecast_signature(forecast["nodes"])
            if not expected or actual != expected:
                raise DingTalkError("流程节点已变化，请重新检测并核对。")
            selections = _node_actioners(task, item["group_id"])
            errors = validate_node_actioners(forecast["nodes"], selections)
            if errors:
                raise DingTalkError("；".join(errors))
            instance_id = await asyncio.to_thread(dingtalk.start_process, form_values, forecast["nodes"], selections, request_id)
            attempt.update({"status": "submitted", "instance_id": instance_id, "updated_at": utc_now()})
        except Exception as exc:
            attempt.update({"status": "failed", "error": str(exc), "updated_at": utc_now()})
        db.save_attempt(attempt)
    attempts = db.approval_attempts(task["id"])
    submitted = sum(1 for attempt in attempts if attempt["status"] == "submitted")
    failed = sum(1 for attempt in attempts if attempt["status"] == "failed")
    final_status = "submitted" if submitted == len(items) else "partial_failed" if submitted else "failed"
    task.update({"status": final_status, "updated_at": utc_now(), "error": None if not failed else f"{failed} 条审批发起失败"})
    db.save_task(task)
    return {"status": final_status, "submitted": submitted, "failed": failed, "items": attempts}


@app.post("/api/tasks/{task_id}/approvals/submit")
async def approval_submit(task_id: str, body: ConfirmSubmit) -> dict[str, Any]:
    if not body.confirm:
        raise HTTPException(status_code=400, detail="正式提交前必须完成批量确认。")
    return await submit_approvals(get_task_or_404(task_id), False)


@app.post("/api/tasks/{task_id}/approvals/retry")
async def approval_retry(task_id: str, body: ConfirmSubmit) -> dict[str, Any]:
    if not body.confirm:
        raise HTTPException(status_code=400, detail="重试前必须确认。")
    return await submit_approvals(get_task_or_404(task_id), True)


def task_file(task_id: str, key: str) -> tuple[Path, str]:
    task = get_task_or_404(task_id)
    raw_path = (task.get("result") or {}).get(key)
    if not raw_path or not Path(raw_path).is_file():
        raise HTTPException(status_code=404, detail="结果文件不存在或尚未生成。")
    path = Path(raw_path)
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
    task = get_task_or_404(task_id)
    departments = (task.get("result") or {}).get("departments", [])
    if index < 0 or index >= len(departments):
        raise HTTPException(status_code=404, detail="付款分组不存在。")
    path = Path(departments[index]["file_path"])
    if not path.is_file():
        raise HTTPException(status_code=404, detail="子表文件不存在。")
    return FileResponse(path, filename=path.name, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.post("/api/tasks/{task_id}/download/selected")
async def download_selected(task_id: str, body: SelectedDownloads) -> StreamingResponse:
    task = get_task_or_404(task_id)
    departments = (task.get("result") or {}).get("departments", [])
    indices = list(dict.fromkeys(body.indices))
    if not indices:
        raise HTTPException(status_code=400, detail="请至少选择一个部门明细文件。")
    if any(index < 0 or index >= len(departments) for index in indices):
        raise HTTPException(status_code=400, detail="选中的部门文件不存在，请刷新后重试。")
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
        for index in indices:
            path = Path(departments[index]["file_path"])
            if not path.is_file():
                raise HTTPException(status_code=404, detail=f"子表文件不存在：{path.name}")
            output.write(path, arcname=path.name)
    archive.seek(0)
    month = str((task.get("result") or {}).get("month") or "当月")
    filename = f"{month}已选部门补贴明细.zip"
    return StreamingResponse(
        archive,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


frontend_dist = ROOT_DIR / "web"
if frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
