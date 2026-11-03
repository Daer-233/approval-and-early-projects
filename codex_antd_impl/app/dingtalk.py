from __future__ import annotations

import json
import os
import hashlib
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)

API_BASE = "https://api.dingtalk.com"
OAPI_BASE = "https://oapi.dingtalk.com"
EXPECTED_FIELDS = ["付款主体", "申请人部门", "供应商名称", "银行账号", "开户行", "成本分摊", "付款方式", "付款类型", "付款金额含税（元）", "付款事由", "部门分摊明细", "发票", "附件"]
FIELD_ALIASES = {"开户行": ("开户行", "开户银行"), "付款金额含税（元）": ("付款金额含税", "付款金额")}
# Kept for loading historic task records created before dynamic node prediction.
APPROVER_ROLES = {
    "director": "项目/设计总监",
    "manager": "项目经理",
    "department_head": "费用发生部门主管",
}


@dataclass(frozen=True)
class DingTalkConfig:
    client_id: str = os.getenv("DINGTALK_CLIENT_ID", "").strip()
    client_secret: str = os.getenv("DINGTALK_CLIENT_SECRET", "").strip()
    agent_id: str = os.getenv("DINGTALK_AGENT_ID", "").strip()
    corp_id: str = os.getenv("DINGTALK_CORP_ID", "").strip()
    originator_user_id: str = os.getenv("DINGTALK_ORIGINATOR_USER_ID", "").strip()
    originator_dept_id: str = os.getenv("DINGTALK_ORIGINATOR_DEPT_ID", "").strip()
    process_code: str = os.getenv("DINGTALK_PROCESS_CODE", "").strip()
    live_submit_enabled: bool = os.getenv("DINGTALK_LIVE_SUBMIT_ENABLED", "false").lower() == "true"
    attachment_enabled: bool = os.getenv("DINGTALK_ATTACHMENT_ENABLED", "false").lower() == "true"

    @property
    def missing(self) -> list[str]:
        values = {
            "Client ID": self.client_id, "Client Secret": self.client_secret, "AgentId": self.agent_id,
            "CorpId": self.corp_id, "固定发起人 UserId": self.originator_user_id,
            "固定发起人 DeptId": self.originator_dept_id, "processCode": self.process_code,
        }
        return [label for label, value in values.items() if not value]

    @property
    def actioner_keys(self) -> dict[str, str]:
        try:
            value = json.loads(os.getenv("DINGTALK_ACTIONER_KEYS_JSON", "{}"))
            return {str(key): str(item) for key, item in value.items()}
        except json.JSONDecodeError:
            return {}


class DingTalkError(RuntimeError):
    pass


class DingTalkClient:
    def __init__(self, config: DingTalkConfig | None = None) -> None:
        self.config = config or DingTalkConfig()
        self._token = ""
        self._token_expires = 0.0

    def public_config(self) -> dict[str, Any]:
        return {
            "configured": not self.config.missing,
            "missing": self.config.missing,
            "process_code": self.config.process_code,
            "agent_id": self.config.agent_id,
            "corp_id": self.config.corp_id,
            "originator_user_id": self.config.originator_user_id,
            "originator_dept_id": self.config.originator_dept_id,
            "live_submit_enabled": self.config.live_submit_enabled,
            "attachment_enabled": self.config.attachment_enabled,
            "dynamic_workflow_nodes": True,
            "legacy_actioner_keys_configured": bool(self.config.actioner_keys),
        }

    def _request(self, method: str, url: str, *, token: bool = True, **kwargs: Any) -> dict[str, Any]:
        headers = dict(kwargs.pop("headers", {}))
        if token:
            headers["x-acs-dingtalk-access-token"] = self.access_token()
        try:
            response = httpx.request(method, url, headers=headers, timeout=30, **kwargs)
            data = response.json()
        except Exception as exc:
            raise DingTalkError(f"钉钉接口连接失败：{exc}") from exc
        if response.is_error:
            message = data.get("message") or data.get("errmsg") or response.text[:300]
            raise DingTalkError(f"钉钉接口返回 {response.status_code}：{message}")
        if data.get("code") not in (None, "", "0", 0) or data.get("errcode") not in (None, 0):
            raise DingTalkError(data.get("message") or data.get("errmsg") or "钉钉接口调用失败")
        return data

    def access_token(self) -> str:
        if self.config.missing:
            raise DingTalkError("钉钉连接资料不完整。")
        if self._token and time.time() < self._token_expires:
            return self._token
        data = self._request("POST", f"{API_BASE}/v1.0/oauth2/accessToken", token=False, json={"appKey": self.config.client_id, "appSecret": self.config.client_secret})
        self._token = data.get("accessToken", "")
        if not self._token:
            raise DingTalkError("钉钉未返回 accessToken。")
        self._token_expires = time.time() + max(60, int(data.get("expireIn", 7200)) - 120)
        return self._token

    def get_schema(self) -> dict[str, Any]:
        data = self._request("GET", f"{API_BASE}/v1.0/workflow/forms/schemas/processCodes", params={"processCode": self.config.process_code})
        return data.get("result", data)

    @staticmethod
    def _schema_items(schema: dict[str, Any]) -> list[dict[str, Any]]:
        content = schema.get("schemaContent", schema)
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except json.JSONDecodeError:
                return []
        return content.get("items", []) if isinstance(content, dict) else []

    @staticmethod
    def _label(item: dict[str, Any]) -> str:
        props = item.get("props") or {}
        return str(props.get("label") or item.get("name") or "").strip()

    def preflight(self, remote: bool = True) -> dict[str, Any]:
        status = self.public_config()
        status.update({"ok": False, "schema_ok": False, "nodes_ok": True, "attachment_ok": False, "messages": []})
        if self.config.missing:
            status["messages"].append("请先在本机 .env 中补充钉钉应用和审批模板资料。")
            return status
        if not remote:
            status["messages"].append("本地配置已读取，尚未向钉钉发起在线预检。")
            return status
        try:
            schema = self.get_schema()
            items = self._schema_items(schema)
            labels = [self._label(item) for item in items]
            missing_fields = [field for field in EXPECTED_FIELDS if not any(any(alias in label for alias in FIELD_ALIASES.get(field, (field.replace("（元）", ""),))) for label in labels)]
            status.update({"schema_ok": not missing_fields, "schema_fields": labels, "missing_schema_fields": missing_fields})
            if missing_fields:
                status["messages"].append("测试审批模板缺少或未识别字段：" + "、".join(missing_fields))
            if self.config.attachment_enabled:
                self.originator_union_id()
                self.approval_space_id()
                status["attachment_ok"] = True
            else:
                status["messages"].append("附件上传仍为安全关闭状态；联调通过后再开启。")
            status["ok"] = bool(status["schema_ok"] and status["nodes_ok"] and status["attachment_ok"])
            if status["ok"]:
                status["messages"].append("表单、审批节点和附件配置预检通过。")
        except DingTalkError as exc:
            status["messages"].append(str(exc))
        return status

    def list_users(self, keyword: str = "", limit: int = 60) -> list[dict[str, str]]:
        token = self.access_token()
        departments = [self.config.originator_dept_id]
        result: list[dict[str, str]] = []
        seen_users: set[str] = set()
        seen_depts: set[str] = set()
        while departments and len(result) < limit:
            dept = departments.pop(0)
            if dept in seen_depts:
                continue
            seen_depts.add(dept)
            child = self._request("POST", f"{OAPI_BASE}/topapi/v2/department/listsubid", token=False, params={"access_token": token}, json={"dept_id": int(dept)})
            departments.extend(str(value) for value in child.get("result", {}).get("dept_id_list", []))
            cursor = 0
            while len(result) < limit:
                page = self._request("POST", f"{OAPI_BASE}/topapi/v2/user/list", token=False, params={"access_token": token}, json={"dept_id": int(dept), "cursor": cursor, "size": 100})
                page_result = page.get("result", {})
                for user in page_result.get("list", []):
                    user_id, name = str(user.get("userid", "")), str(user.get("name", ""))
                    if user_id and user_id not in seen_users and (not keyword or keyword.lower() in name.lower() or keyword.lower() in user_id.lower()):
                        result.append({"user_id": user_id, "name": name, "dept_id": dept})
                        seen_users.add(user_id)
                if not page_result.get("has_more"):
                    break
                cursor = int(page_result.get("next_cursor", cursor + 100))
        return result[:limit]

    def originator_union_id(self) -> str:
        token = self.access_token()
        data = self._request(
            "POST",
            f"{OAPI_BASE}/topapi/v2/user/get",
            token=False,
            params={"access_token": token},
            json={"userid": self.config.originator_user_id},
        )
        union_id = str((data.get("result") or {}).get("unionid", "")).strip()
        if not union_id:
            raise DingTalkError("未取得固定发起人的 unionId，请检查通讯录用户读取权限和 UserId。")
        return union_id

    def approval_space_id(self) -> str:
        data = self._request(
            "POST",
            f"{API_BASE}/v1.0/workflow/processInstances/spaces/infos/query",
            json={"userId": self.config.originator_user_id, "agentId": int(self.config.agent_id)},
        )
        result = data.get("result", data)
        space_id = str(result.get("spaceId", "")).strip()
        if not space_id:
            raise DingTalkError("未取得审批钉盘空间，请检查 Workflow.Instance.Write 权限。")
        return space_id

    def forecast(self, form_values: list[dict[str, Any]]) -> dict[str, Any]:
        payload = {"requestId": uuid.uuid4().hex, "processCode": self.config.process_code, "deptId": int(self.config.originator_dept_id), "userId": self.config.originator_user_id, "formComponentValues": form_values}
        return self._request("POST", f"{API_BASE}/v1.0/workflow/processes/forecast", json=payload).get("result", {})

    def start_process(
        self,
        form_values: list[dict[str, Any]],
        nodes: list[dict[str, Any]],
        node_actioners: dict[str, list[dict[str, str]]],
        request_id: str,
    ) -> str:
        if not self.config.live_submit_enabled:
            raise DingTalkError("正式提交开关未开启。请先用测试审批模板完成联调。")
        errors = validate_node_actioners(nodes, node_actioners)
        if errors:
            raise DingTalkError("；".join(errors))
        actioners = build_target_select_actioners(nodes, node_actioners)
        payload = {
            "originatorUserId": self.config.originator_user_id,
            "processCode": self.config.process_code,
            "deptId": int(self.config.originator_dept_id),
            "microappAgentId": int(self.config.agent_id),
            "targetSelectActioners": actioners,
            "formComponentValues": form_values,
            "requestId": request_id,
        }
        data = self._request("POST", f"{API_BASE}/v1.0/workflow/processInstances", json=payload)
        instance_id = data.get("instanceId") or data.get("result", {}).get("instanceId")
        if not instance_id:
            raise DingTalkError("钉钉未返回审批实例 ID。")
        return str(instance_id)

    def upload_approval_attachment(self, file_path: Path) -> dict[str, str]:
        if not self.config.attachment_enabled:
            raise DingTalkError("附件上传开关未开启。")
        space_id = self.approval_space_id()
        union_id = self.originator_union_id()
        upload_url = f"{API_BASE}/v1.0/storage/spaces/{space_id}/files/uploadInfos/query"
        commit_url = f"{API_BASE}/v1.0/storage/spaces/{space_id}/files/commit"
        request_body = {
            "protocol": "HEADER_SIGNATURE",
            "multipart": False,
            "option": {
                "storageDriver": "DINGTALK",
                "preCheckParam": {"name": file_path.name, "size": file_path.stat().st_size, "parentId": "0"},
            },
        }
        info_data = self._request("POST", upload_url, params={"unionId": union_id}, json=request_body)
        info = info_data.get("result", info_data)
        header_info = info.get("headerSignatureInfo") or {}
        resource_urls = header_info.get("resourceUrls") or []
        if not resource_urls:
            raise DingTalkError("钉钉未返回附件上传地址。")
        with file_path.open("rb") as source:
            response = httpx.put(resource_urls[0], content=source.read(), headers=header_info.get("headers") or {}, timeout=120)
        if response.is_error:
            raise DingTalkError(f"附件二进制上传失败：HTTP {response.status_code}")
        commit_data = self._request(
            "POST",
            commit_url,
            params={"unionId": union_id},
            json={
                "uploadKey": info.get("uploadKey"),
                "name": file_path.name,
                "parentId": "0",
                "option": {"size": file_path.stat().st_size, "conflictStrategy": "AUTO_RENAME"},
            },
        )
        commit = commit_data.get("result", commit_data)
        dentry = commit.get("dentry") or commit
        file_id = str(dentry.get("id") or dentry.get("dentryUuid") or dentry.get("fileId") or "")
        if not file_id:
            raise DingTalkError("附件提交成功但未返回 fileId。")
        return {"fileId": file_id, "fileName": file_path.name, "fileType": file_path.suffix.lstrip("."), "spaceId": space_id, "fileSize": str(file_path.stat().st_size)}


def _strings_from_range(value: Any, key: str = "") -> set[str]:
    """Extract explicit user identifiers from the forecast selection range."""
    identifiers: set[str] = set()
    id_keys = {"userid", "userids", "workno", "worknos", "useridlist", "userlist"}
    if isinstance(value, dict):
        for child_key, child_value in value.items():
            identifiers.update(_strings_from_range(child_value, str(child_key).lower()))
    elif isinstance(value, list):
        for item in value:
            identifiers.update(_strings_from_range(item, key))
    elif isinstance(value, (str, int)) and key.lower() in id_keys:
        text = str(value).strip()
        if text:
            identifiers.add(text)
    return identifiers


def _forecast_actioners(value: Any) -> list[dict[str, str]]:
    actioners = value if isinstance(value, list) else []
    result: list[dict[str, str]] = []
    for actioner in actioners:
        if not isinstance(actioner, dict):
            continue
        user_id = str(actioner.get("userId") or actioner.get("userid") or actioner.get("workNo") or "").strip()
        name = str(actioner.get("name") or actioner.get("userName") or user_id).strip()
        if user_id:
            result.append({"user_id": user_id, "name": name})
    return result


def normalize_forecast(forecast: dict[str, Any]) -> dict[str, Any]:
    """Convert DingTalk's variable-shaped forecast payload to a stable task format."""
    rules = forecast.get("workflowActivityRules") or []
    nodes: list[dict[str, Any]] = []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        workflow_actor = rule.get("workflowActor") or {}
        activity_type = str(rule.get("activityType") or "")
        target_select = bool(rule.get("isTargetSelect")) or activity_type == "target_select"
        actor_key = str(workflow_actor.get("actorKey") or rule.get("actorKey") or rule.get("actionerKey") or "").strip()
        raw_range = workflow_actor.get("actorSelectionRange") or rule.get("actorSelectionRange") or {}
        restricted = bool(raw_range)
        nodes.append({
            "activity_id": str(rule.get("activityId") or "").strip(),
            "name": str(rule.get("activityName") or "审批节点").strip(),
            "kind": "manual" if target_select else "fixed",
            "activity_type": activity_type,
            "actor_key": actor_key,
            "required": bool(workflow_actor.get("required")) if target_select else False,
            "allowed_multi": bool(workflow_actor.get("allowedMulti")),
            "approval_method": str(workflow_actor.get("approvalMethod") or ""),
            "activation_type": str(workflow_actor.get("actorActivateType") or ""),
            "fixed_actioners": _forecast_actioners(rule.get("activityActioners")),
            "allowed_user_ids": sorted(_strings_from_range(raw_range)),
            "selection_range_restricted": restricted,
            "selection_range_resolvable": not restricted or bool(_strings_from_range(raw_range)),
        })
    return {
        "success": bool(forecast.get("isForecastSuccess", True)),
        "static_workflow": bool(forecast.get("isStaticWorkflow")),
        "nodes": nodes,
    }


def forecast_signature(nodes: list[dict[str, Any]]) -> str:
    stable = [{
        "activity_id": node.get("activity_id", ""), "kind": node.get("kind", ""),
        "actor_key": node.get("actor_key", ""), "required": bool(node.get("required")),
        "allowed_multi": bool(node.get("allowed_multi")),
        "allowed_user_ids": node.get("allowed_user_ids", []),
    } for node in nodes]
    source = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def validate_node_actioners(nodes: list[dict[str, Any]], node_actioners: dict[str, list[dict[str, str]]]) -> list[str]:
    errors: list[str] = []
    for node in nodes:
        if node.get("kind") != "manual":
            continue
        name, actor_key = str(node.get("name") or "审批节点"), str(node.get("actor_key") or "")
        users = node_actioners.get(actor_key, []) if actor_key else []
        user_ids = [str(item.get("user_id") or "").strip() for item in users if str(item.get("user_id") or "").strip()]
        if not actor_key:
            errors.append(f"{name} 未返回 actionerKey，无法提交")
        if node.get("selection_range_restricted") and not node.get("selection_range_resolvable"):
            errors.append(f"{name} 的可选人员范围无法识别，请在钉钉模板中明确配置人员范围")
        if node.get("required") and not user_ids:
            errors.append(f"{name} 为必选审批节点")
        if not node.get("allowed_multi") and len(user_ids) > 1:
            errors.append(f"{name} 仅允许选择一位审批人")
        allowed = set(node.get("allowed_user_ids") or [])
        if allowed and any(user_id not in allowed for user_id in user_ids):
            errors.append(f"{name} 包含不在钉钉允许范围内的人员")
    return errors


def build_target_select_actioners(nodes: list[dict[str, Any]], node_actioners: dict[str, list[dict[str, str]]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for node in nodes:
        if node.get("kind") != "manual":
            continue
        actor_key = str(node.get("actor_key") or "")
        user_ids = [str(item.get("user_id") or "").strip() for item in node_actioners.get(actor_key, [])]
        user_ids = [user_id for user_id in user_ids if user_id]
        if user_ids:
            result.append({"actionerKey": actor_key, "actionerUserIds": user_ids})
    return result


def chinese_upper_money(value: float | int) -> str:
    value = round(float(value) + 1e-8, 2)
    if value == 0:
        return "零元整"
    digits, units, section_units = "零壹贰叁肆伍陆柒捌玖", ["", "拾", "佰", "仟"], ["", "万", "亿", "兆"]
    integer, decimal = int(value), int(round((value - int(value)) * 100))
    sections, section_index = [], 0
    while integer:
        section = integer % 10000
        if section:
            text, zero = "", False
            for index in range(4):
                digit = section % 10
                if digit:
                    text = digits[digit] + units[index] + text
                    if zero:
                        text = digits[0] + text
                    zero = False
                elif text:
                    zero = True
                section //= 10
            sections.insert(0, text + section_units[section_index])
        elif sections and not sections[0].startswith(digits[0]):
            sections.insert(0, digits[0])
        integer //= 10000
        section_index += 1
    result = "".join(sections).replace("零零", "零").rstrip("零") + "元"
    jiao, fen = divmod(decimal, 10)
    if jiao:
        result += digits[jiao] + "角"
    elif fen:
        result += "零"
    if fen:
        result += digits[fen] + "分"
    elif not jiao:
        result += "整"
    return result


def build_display_fields(group: dict[str, Any], profile: dict[str, str], month: str, attachment_name: str, originator_dept_id: str = "") -> list[dict[str, Any]]:
    amount = group["amount"]
    return [
        {"name": "付款主体", "value": profile.get("payment_entity", "")}, {"name": "申请人部门", "value": originator_dept_id}, {"name": "关联审批单", "value": ""},
        {"name": "供应商名称", "value": profile.get("supplier_name", "")}, {"name": "银行账号", "value": profile.get("bank_account", "")},
        {"name": "开户行", "value": profile.get("bank_name", "")}, {"name": "成本分摊", "value": "部门费用"},
        {"name": "付款方式", "value": "银行转账"}, {"name": "付款类型", "value": "付全款"},
        {"name": "付款金额含税（元）", "value": amount}, {"name": "大写", "value": chinese_upper_money(amount)},
        {"name": "付款事由", "value": f"{group['payment_department']}{month}餐补发放"}, {"name": "项目分摊明细", "value": ""},
        {"name": "部门分摊明细", "value": [{"费用科目": "福利费", "发生费用部门": group["payment_department"], "金额（元）": amount}]},
        {"name": "备注", "value": ""}, {"name": "发票", "value": "增值税普通发票"},
        {"name": "附件", "value": attachment_name}, {"name": "发送到聊天", "value": ""},
    ]


def form_values_from_schema(schema: dict[str, Any], display_fields: Iterable[dict[str, Any]], attachment: dict[str, str] | None = None) -> list[dict[str, Any]]:
    fields = {field["name"]: field["value"] for field in display_fields}
    result: list[dict[str, Any]] = []
    for item in DingTalkClient._schema_items(schema):
        props = item.get("props") or {}
        label = DingTalkClient._label(item)
        match = next((name for name in fields if name == label or any(alias in label for alias in FIELD_ALIASES.get(name, (name.replace("（元）", ""),)))), None)
        if not match:
            continue
        value = fields[match]
        if match == "附件":
            value = json.dumps([attachment], ensure_ascii=False) if attachment else ""
        elif isinstance(value, (list, dict)):
            value = json.dumps(value, ensure_ascii=False)
        result.append({"id": props.get("id") or item.get("id"), "name": label, "value": str(value), "componentType": item.get("componentName") or item.get("componentType")})
    return result
