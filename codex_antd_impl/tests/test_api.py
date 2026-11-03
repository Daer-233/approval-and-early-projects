from __future__ import annotations

import importlib
import os
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.splitter import HEADERS
from app.dingtalk import build_target_select_actioners, forecast_signature, normalize_forecast, validate_node_actioners


class ApiTest(unittest.TestCase):
    def test_upload_prepare_persistence_and_preview(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            os.environ["APP_DATA_DIR"] = str(Path(temp) / "data")
            main = importlib.import_module("app.main")
            client = TestClient(main.app)
            source = Path(temp) / "8月.xlsx"
            wb = Workbook(); ws = wb.active; ws.cell(1, 1, "2026年8月补贴明细"); ws.append(HEADERS)
            ws.append([1, "深圳再造", "甲", "供应链中心", "采购部", "采购组", 100, 20, 0, None, ""])
            ws.append([2, "新进化", "乙", "创新中心", "产品部", "新组", 80, 0, 0, None, ""])
            wb.save(source)
            with source.open("rb") as stream:
                created = client.post("/api/tasks", files={"file": (source.name, stream, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
            self.assertEqual(created.status_code, 200, created.text)
            task = created.json(); self.assertEqual(task["status"], "review"); self.assertEqual(task["analysis"]["actual_groups"], 2)
            groups = []
            for group in task["analysis"]["groups"]:
                groups.append({"group_id": group["id"], "selected": True, "payment_department": group["payment_department"] or "创新组", "approvers": {role: {"user_id": role + "1", "name": role} for role in ("director", "manager", "department_head")}})
            saved = client.put(f"/api/tasks/{task['id']}/groups", json={"groups": groups})
            self.assertEqual(saved.status_code, 200, saved.text)
            prepared = client.post(f"/api/tasks/{task['id']}/prepare", json={})
            self.assertEqual(prepared.status_code, 200, prepared.text)
            self.assertEqual(prepared.json()["result"]["payment_departments"], 2)
            selected_download = client.post(f"/api/tasks/{task['id']}/download/selected", json={"indices": [0, 1]})
            self.assertEqual(selected_download.status_code, 200, selected_download.text)
            self.assertEqual(selected_download.headers["content-type"], "application/zip")
            self.assertTrue(selected_download.content.startswith(b"PK"))
            with ZipFile(BytesIO(selected_download.content)) as archive:
                self.assertEqual(len(archive.namelist()), 2)
            preview = client.post(f"/api/tasks/{task['id']}/approvals/preview", json={})
            self.assertEqual(preview.status_code, 200, preview.text)
            self.assertFalse(preview.json()["valid"])  # Company profiles intentionally missing.
            self.assertEqual(client.get("/api/tasks").json()["items"][0]["id"], task["id"])


class ForecastNodeTest(unittest.TestCase):
    def test_normalizes_fixed_and_manual_nodes_and_validates_selection(self) -> None:
        raw = {
            "isForecastSuccess": True,
            "workflowActivityRules": [
                {"activityId": "fixed", "activityName": "固定审批", "isTargetSelect": False,
                 "workflowActor": {"required": False}, "activityActioners": [{"name": "黄晓熙", "userId": "fixed-user"}]},
                {"activityId": "single", "activityName": "项目经理", "isTargetSelect": True,
                 "workflowActor": {"actorKey": "manager-key", "required": True, "allowedMulti": False,
                                   "actorSelectionRange": {"userIds": ["u1", "u2"]}}},
                {"activityId": "multi", "activityName": "抄送审批", "activityType": "target_select",
                 "workflowActor": {"actorKey": "multi-key", "required": False, "allowedMulti": True}},
            ],
        }
        nodes = normalize_forecast(raw)["nodes"]
        self.assertEqual(nodes[0]["kind"], "fixed")
        self.assertEqual(nodes[0]["fixed_actioners"][0]["name"], "黄晓熙")
        self.assertEqual(nodes[1]["allowed_user_ids"], ["u1", "u2"])
        self.assertTrue(validate_node_actioners(nodes, {}))
        actioners = {"manager-key": [{"user_id": "u1", "name": "甲"}], "multi-key": [{"user_id": "u2", "name": "乙"}, {"user_id": "u1", "name": "甲"}]}
        self.assertEqual(validate_node_actioners(nodes, actioners), [])
        self.assertEqual(build_target_select_actioners(nodes, actioners), [{"actionerKey": "manager-key", "actionerUserIds": ["u1"]}, {"actionerKey": "multi-key", "actionerUserIds": ["u2", "u1"]}])
        self.assertNotEqual(forecast_signature(nodes), forecast_signature(nodes[:2]))

    def test_rejects_out_of_range_and_ambiguous_range(self) -> None:
        nodes = normalize_forecast({"workflowActivityRules": [{"activityId": "a", "activityName": "审批人", "isTargetSelect": True,
            "workflowActor": {"actorKey": "key", "required": True, "allowedMulti": False, "actorSelectionRange": {"departments": ["1"]}}}]})["nodes"]
        errors = validate_node_actioners(nodes, {"key": [{"user_id": "someone", "name": "某人"}]})
        self.assertTrue(any("无法识别" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
