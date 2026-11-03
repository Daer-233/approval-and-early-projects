from __future__ import annotations

import argparse
import re
import sys
import zipfile
from collections import OrderedDict
from copy import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Mapping, Sequence

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

HEADERS = [
    "序号", "公司主体", "姓名", "一级部门", "二级部门", "三级部门",
    "日常餐补", "宵夜餐补", "出差餐补", "合计/元", "备注",
]

TITLE_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FILL = PatternFill("solid", fgColor="D9EAF7")
TOTAL_FILL = PatternFill("solid", fgColor="FFF2CC")
THIN_SIDE = Side(style="thin", color="B7C9D6")
ALL_BORDER = Border(left=THIN_SIDE, right=THIN_SIDE, top=THIN_SIDE, bottom=THIN_SIDE)
FONT_NAME = "Microsoft YaHei"


def clean_text(value: object) -> str:
    return "" if value is None else str(value).strip()


def to_number(value: object) -> float:
    if value in (None, ""):
        return 0.0
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    text = clean_text(value).replace(",", "")
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(f"餐补金额不是有效数字：{value!r}") from exc


def display_number(value: float) -> int | float:
    return int(value) if float(value).is_integer() else round(value, 2)


def extract_month(title: str, file_name: str) -> tuple[str, str]:
    match = re.search(r"(1[0-2]|[1-9])\s*月", title) or re.search(r"(1[0-2]|[1-9])\s*月", file_name)
    if match:
        short = f"{int(match.group(1))}月"
        return short, f"{int(match.group(1))}月份"
    return "当月", "当月"


def find_header_row(ws: Worksheet) -> tuple[int, Dict[str, int]]:
    aliases = {
        "公司主体": "公司主体",
        "姓名": "姓名",
        "一级部门": "一级部门",
        "二级部门": "二级部门",
        "三级部门": "三级部门",
        "日常餐补": "日常餐补",
        "宵夜餐补": "宵夜餐补",
        "夜宵餐补": "宵夜餐补",
        "出差餐补": "出差餐补",
        "合计/元": "合计/元",
        "备注": "备注",
        "序号": "序号",
    }
    required = {"公司主体", "姓名", "一级部门", "二级部门", "三级部门", "日常餐补", "宵夜餐补", "出差餐补"}
    for row in ws.iter_rows(min_row=1, max_row=min(ws.max_row, 30)):
        mapping: Dict[str, int] = {}
        for cell in row:
            key = aliases.get(clean_text(cell.value))
            if key:
                mapping[key] = cell.column
        if required.issubset(mapping):
            return row[0].row, mapping
    raise ValueError("未找到表头。请确保包含：公司主体、姓名、一级部门、二级部门、三级部门、日常餐补、宵夜餐补、出差餐补。")


def read_rows(input_path: Path) -> tuple[List[Dict[str, object]], str]:
    try:
        wb = load_workbook(input_path, data_only=False)
    except Exception as exc:
        raise RuntimeError(
            f"无法读取 {input_path.name}。请使用可编辑、未加密的 .xlsx 副本作为输入文件。"
        ) from exc
    ws = wb.active
    header_row, col = find_header_row(ws)
    title = clean_text(ws.cell(1, 1).value) or input_path.stem
    rows: List[Dict[str, object]] = []
    for excel_row in range(header_row + 1, ws.max_row + 1):
        company = clean_text(ws.cell(excel_row, col["公司主体"]).value)
        name = clean_text(ws.cell(excel_row, col["姓名"]).value)
        # 仅保留真实明细；自动跳过“合计/总计”行、空行和说明行。
        if not company or company in {"合计", "总计"}:
            continue
        if not name:
            continue
        values = {
            "公司主体": company,
            "姓名": name,
            "一级部门": clean_text(ws.cell(excel_row, col["一级部门"]).value),
            "二级部门": clean_text(ws.cell(excel_row, col["二级部门"]).value),
            "三级部门": clean_text(ws.cell(excel_row, col["三级部门"]).value),
            "日常餐补": to_number(ws.cell(excel_row, col["日常餐补"]).value),
            "宵夜餐补": to_number(ws.cell(excel_row, col["宵夜餐补"]).value),
            "出差餐补": to_number(ws.cell(excel_row, col["出差餐补"]).value),
            "备注": clean_text(ws.cell(excel_row, col.get("备注", 0)).value) if col.get("备注") else "",
        }
        rows.append(values)
    if not rows:
        raise ValueError("未读取到有效费用明细。")
    return rows, title


@dataclass(frozen=True)
class PaymentRule:
    filename_stem: str
    payment_department: str
    company: str
    scope: str
    predicate: Callable[[Mapping[str, object]], bool]


def build_rules(month: str) -> List[PaymentRule]:
    return [
        PaymentRule(f"财务管理中心{month}补贴明细", "财务管理中心", "深圳再造", "财务管理中心", lambda r: r["公司主体"] == "深圳再造" and r["一级部门"] == "财务管理中心"),
        PaymentRule(f"发展中心{month}补贴明细", "发展中心", "新进化", "发展中心", lambda r: r["公司主体"] == "新进化" and r["一级部门"] == "发展中心"),
        PaymentRule(f"供应链中心{month}补贴明细", "供应链中心", "深圳再造", "仓储物流部、质检组、采购部", lambda r: r["公司主体"] == "深圳再造" and r["一级部门"] == "供应链中心"),
        PaymentRule(f"人力资源组{month}补贴明细", "人力资源组", "深圳再造", "人力资源组、薪酬绩效组", lambda r: r["公司主体"] == "深圳再造" and r["一级部门"] == "人力行政中心" and r["二级部门"] in {"人力资源组", "薪酬绩效组"}),
        PaymentRule(f"软装A、B组{month}补贴明细", "软装A、B组", "新进化", "软装深圳A组、软装深圳B组", lambda r: r["公司主体"] == "新进化" and r["三级部门"] in {"软装深圳A组", "软装深圳B组"}),
        PaymentRule(f"软装C组{month}补贴明细", "软装C组", "新进化", "软装深圳C组", lambda r: r["公司主体"] == "新进化" and r["三级部门"] == "软装深圳C组"),
        PaymentRule(f"软装D组{month}补贴明细", "软装D组", "新进化", "软装深圳D组", lambda r: r["公司主体"] == "新进化" and r["三级部门"] == "软装深圳D组"),
        PaymentRule(f"软装上海组{month}补贴明细-上海再造", "软装上海组", "上海再造", "软装上海组", lambda r: r["公司主体"] == "上海再造" and r["三级部门"] == "软装上海组"),
        PaymentRule(f"软装上海组{month}补贴明细-新进化", "软装上海组", "新进化", "软装上海组", lambda r: r["公司主体"] == "新进化" and r["三级部门"] == "软装上海组"),
        PaymentRule(f"上海人力行政中心{month}补贴明细", "上海人力行政中心", "上海再造", "上海中心", lambda r: r["公司主体"] == "上海再造" and r["一级部门"] == "人力行政中心"),
        PaymentRule(f"行政管理组{month}补贴明细-老进化", "行政管理组", "老进化", "行政管理组", lambda r: r["公司主体"] == "老进化" and r["三级部门"] == "行政管理组"),
        PaymentRule(f"行政管理组{month}补贴明细-深圳再造", "行政管理组", "深圳再造", "行政管理组", lambda r: r["公司主体"] == "深圳再造" and r["三级部门"] == "行政管理组"),
        PaymentRule(f"营销及品牌部{month}补贴明细", "营销及品牌部", "深圳再造", "营销及品牌部", lambda r: r["公司主体"] == "深圳再造" and r["一级部门"] == "营销及品牌部"),
        PaymentRule(f"硬装地产组{month}补贴明细-上海再造", "硬装地产组", "上海再造", "地产组 / 上海组", lambda r: r["公司主体"] == "上海再造" and r["一级部门"] == "硬装事业部" and r["二级部门"] == "地产组"),
        PaymentRule(f"硬装地产组{month}补贴明细-新进化", "硬装地产组", "新进化", "地产组 / 地产组、设计A组", lambda r: r["公司主体"] == "新进化" and r["一级部门"] == "硬装事业部" and r["二级部门"] == "地产组"),
        PaymentRule(f"硬装技术组{month}补贴明细", "硬装技术组", "新进化", "技术组 / 技术组、施工图组、表现组、物料组", lambda r: r["公司主体"] == "新进化" and r["一级部门"] == "硬装事业部" and r["二级部门"] == "技术组"),
        PaymentRule(f"硬装商业组{month}补贴明细", "硬装商业组", "新进化", "商业组", lambda r: r["公司主体"] == "新进化" and r["一级部门"] == "硬装事业部" and r["二级部门"] == "商业组"),
        PaymentRule(f"总经办{month}补贴明细-老进化", "总经办", "老进化", "总经办", lambda r: r["公司主体"] == "老进化" and r["一级部门"] == "总经办"),
        PaymentRule(f"总经办{month}补贴明细-再造", "总经办", "深圳再造", "总经办", lambda r: r["公司主体"] == "深圳再造" and r["一级部门"] == "总经办"),
    ]


def set_sheet_title(ws: Worksheet, title: str, last_col: int) -> None:
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last_col)
    cell = ws.cell(1, 1, title)
    cell.fill = TITLE_FILL
    cell.font = Font(name=FONT_NAME, size=14, bold=True, color="FFFFFF")
    cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 28


def style_headers(ws: Worksheet, row: int, last_col: int) -> None:
    for col in range(1, last_col + 1):
        c = ws.cell(row, col)
        c.fill = HEADER_FILL
        c.font = Font(name=FONT_NAME, bold=True)
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = ALL_BORDER
    ws.row_dimensions[row].height = 28


def apply_table_style(ws: Worksheet, start_row: int, end_row: int, last_col: int, numeric_cols: Iterable[int]) -> None:
    numeric_cols = set(numeric_cols)
    for row in ws.iter_rows(min_row=start_row, max_row=end_row, min_col=1, max_col=last_col):
        for c in row:
            c.border = ALL_BORDER
            c.font = Font(name=FONT_NAME, size=10)
            c.alignment = Alignment(horizontal="right" if c.column in numeric_cols else "center", vertical="center", wrap_text=(c.column == last_col))
            if c.column in numeric_cols:
                c.number_format = '#,##0.00;[Red]-#,##0.00'


def set_detail_widths(ws: Worksheet) -> None:
    widths = [8, 14, 12, 15, 15, 16, 12, 12, 12, 12, 28]
    for col, width in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(col)].width = width


def write_detail_workbook(rows: Sequence[Mapping[str, object]], rule: PaymentRule, path: Path, title: str) -> Dict[str, float]:
    wb = Workbook()
    ws = wb.active
    ws.title = "补贴明细"
    ws.sheet_view.showGridLines = False
    set_sheet_title(ws, title, 11)
    ws.append(HEADERS)
    style_headers(ws, 2, 11)

    daily = night = travel = 0.0
    for index, row in enumerate(rows, start=1):
        excel_row = index + 2
        daily_value = to_number(row["日常餐补"])
        night_value = to_number(row["宵夜餐补"])
        travel_value = to_number(row["出差餐补"])
        daily += daily_value
        night += night_value
        travel += travel_value
        ws.append([
            index, row["公司主体"], row["姓名"], row["一级部门"], row["二级部门"], row["三级部门"],
            display_number(daily_value), display_number(night_value), display_number(travel_value),
            f"=SUM(G{excel_row}:I{excel_row})", row.get("备注", ""),
        ])
    last_data_row = 2 + len(rows)
    total_row = last_data_row + 1
    ws.cell(total_row, 1, "合计")
    ws.cell(total_row, 7, f"=SUM(G3:G{last_data_row})")
    ws.cell(total_row, 8, f"=SUM(H3:H{last_data_row})")
    ws.cell(total_row, 9, f"=SUM(I3:I{last_data_row})")
    ws.cell(total_row, 10, f"=SUM(G{total_row}:I{total_row})")
    ws.cell(total_row, 11, "付款金额＝日常餐补＋宵夜餐补＋出差餐补")
    apply_table_style(ws, 3, total_row, 11, {7, 8, 9, 10})
    for cell in ws[total_row]:
        cell.fill = TOTAL_FILL
        cell.font = Font(name=FONT_NAME, bold=True)
    set_detail_widths(ws)
    ws.freeze_panes = "A3"
    ws.auto_filter.ref = f"A2:K{last_data_row}"
    wb.calculation.fullCalcOnLoad = True
    wb.calculation.forceFullCalc = True
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return {"count": float(len(rows)), "daily": daily, "night": night, "travel": travel, "amount": daily + night + travel}


def write_summary_workbook(all_rows: Sequence[Mapping[str, object]], results: Sequence[Dict[str, object]], path: Path, title: str, month: str) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "付款汇总"
    ws.sheet_view.showGridLines = False
    set_sheet_title(ws, f"{title}—付款部门拆分汇总（19份）", 10)
    headers = ["序号", "付款部门", "公司主体", "部门口径（原始二/三级部门）", "人数", "日常餐补", "宵夜餐补", "出差餐补", "付款金额", "子表文件名"]
    ws.append(headers)
    style_headers(ws, 2, 10)
    for idx, item in enumerate(results, start=1):
        row_number = idx + 2
        ws.append([
            idx, item["payment_department"], item["company"], item["scope"], int(item["count"]),
            display_number(item["daily"]), display_number(item["night"]), display_number(item["travel"]),
            f"=SUM(F{row_number}:H{row_number})", item["file_name"],
        ])
    last_data_row = 2 + len(results)
    total_row = last_data_row + 1
    ws.cell(total_row, 1, "合计")
    ws.cell(total_row, 5, f"=SUM(E3:E{last_data_row})")
    ws.cell(total_row, 6, f"=SUM(F3:F{last_data_row})")
    ws.cell(total_row, 7, f"=SUM(G3:G{last_data_row})")
    ws.cell(total_row, 8, f"=SUM(H3:H{last_data_row})")
    ws.cell(total_row, 9, f"=SUM(F{total_row}:H{total_row})")
    ws.cell(total_row, 10, "共19个付款部门")
    apply_table_style(ws, 3, total_row, 10, {5, 6, 7, 8, 9})
    for row in range(3, total_row + 1):
        ws.cell(row, 5).number_format = "#,##0"
    for c in ws[total_row]:
        c.fill = TOTAL_FILL
        c.font = Font(name=FONT_NAME, bold=True)
    widths = [7, 18, 14, 40, 8, 12, 12, 12, 12, 36]
    for col, width in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.freeze_panes = "A3"
    ws.auto_filter.ref = f"A2:J{last_data_row}"

    raw = wb.create_sheet("原始明细（已重算）")
    raw.sheet_view.showGridLines = False
    set_sheet_title(raw, f"{title}（不含总计行）", 11)
    raw.append(HEADERS)
    style_headers(raw, 2, 11)
    for index, row in enumerate(all_rows, start=1):
        excel_row = index + 2
        raw.append([
            index, row["公司主体"], row["姓名"], row["一级部门"], row["二级部门"], row["三级部门"],
            display_number(to_number(row["日常餐补"])), display_number(to_number(row["宵夜餐补"])), display_number(to_number(row["出差餐补"])),
            f"=SUM(G{excel_row}:I{excel_row})", row.get("备注", ""),
        ])
    last_raw_row = 2 + len(all_rows)
    apply_table_style(raw, 3, last_raw_row, 11, {7, 8, 9, 10})
    set_detail_widths(raw)
    raw.freeze_panes = "A3"
    raw.auto_filter.ref = f"A2:K{last_raw_row}"

    notes = wb.create_sheet("使用说明")
    notes.sheet_view.showGridLines = False
    set_sheet_title(notes, "使用说明", 2)
    notes_rows = [
        ("金额规则", "不读取原表“合计/元”列；逐行重新计算：日常餐补＋宵夜餐补＋出差餐补。"),
        ("原始明细", "“原始明细（已重算）”保留费用明细，不包含原总表的总计行。"),
        ("子表合计", "19份付款子表均在末行添加“合计”；付款金额为三类餐补之和。"),
        ("供应链中心", "仓储物流部、质检组、采购部合并为1个付款部门。"),
        ("人力资源组", "人力资源组、薪酬绩效组合并为1个付款部门。"),
        ("硬装技术组", "技术组、施工图组、表现组、物料组合并为1个付款部门。"),
        ("当月文件", f"本次按{month}生成19份子表及1份带总计行的付款汇总表。"),
    ]
    for row_index, (label, text) in enumerate(notes_rows, start=3):
        notes.cell(row_index, 1, label)
        notes.cell(row_index, 2, text)
    for row in notes.iter_rows(min_row=3, max_row=2 + len(notes_rows), min_col=1, max_col=2):
        for c in row:
            c.border = ALL_BORDER
            c.font = Font(name=FONT_NAME, bold=(c.column == 1))
            c.fill = HEADER_FILL if c.column == 1 else PatternFill(fill_type=None)
            c.alignment = Alignment(vertical="center", wrap_text=True)
    notes.column_dimensions["A"].width = 18
    notes.column_dimensions["B"].width = 78
    for r in range(3, 3 + len(notes_rows)):
        notes.row_dimensions[r].height = 30

    wb.calculation.fullCalcOnLoad = True
    wb.calculation.forceFullCalc = True
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def split_payment_allowances(input_path: Path, output_root: Path) -> Dict[str, object]:
    rows, title = read_rows(input_path)
    short_month, full_month = extract_month(title, input_path.stem)
    rules = build_rules(short_month)
    run_dir = output_root / f"{full_month}补贴_付款拆分_修正版"
    child_dir = run_dir / f"{full_month}补贴_付款部门文件_19份"
    child_dir.mkdir(parents=True, exist_ok=True)

    claimed: set[int] = set()
    results: List[Dict[str, object]] = []
    for rule in rules:
        indices = [idx for idx, row in enumerate(rows) if rule.predicate(row)]
        if not indices:
            raise ValueError(f"付款规则无匹配明细：{rule.filename_stem}")
        duplicate = claimed.intersection(indices)
        if duplicate:
            raise ValueError(f"存在被多个付款部门重复归集的明细：{sorted(duplicate)[:5]}")
        claimed.update(indices)
        matched = [rows[idx] for idx in indices]
        detail_path = child_dir / f"{rule.filename_stem}.xlsx"
        amounts = write_detail_workbook(matched, rule, detail_path, title)
        results.append({
            "payment_department": rule.payment_department,
            "company": rule.company,
            "scope": rule.scope,
            "file_name": detail_path.name,
            **amounts,
        })
    if len(results) != 19:
        raise AssertionError(f"付款部门数量异常：{len(results)}")
    if len(claimed) != len(rows):
        not_matched = [rows[idx] for idx in range(len(rows)) if idx not in claimed]
        names = "、".join(str(r["姓名"]) for r in not_matched[:10])
        raise ValueError(f"存在未归集明细（共{len(not_matched)}条）：{names}")

    raw_daily = sum(to_number(r["日常餐补"]) for r in rows)
    raw_night = sum(to_number(r["宵夜餐补"]) for r in rows)
    raw_travel = sum(to_number(r["出差餐补"]) for r in rows)
    detail_daily = sum(float(r["daily"]) for r in results)
    detail_night = sum(float(r["night"]) for r in results)
    detail_travel = sum(float(r["travel"]) for r in results)
    if (raw_daily, raw_night, raw_travel) != (detail_daily, detail_night, detail_travel):
        raise AssertionError("拆分前后餐补金额不一致。")

    summary_path = run_dir / f"{full_month}补贴_付款部门拆分汇总_19份_修正版.xlsx"
    write_summary_workbook(rows, results, summary_path, title, short_month)
    zip_path = run_dir / f"{full_month}补贴_按付款部门拆分_19份_修正版.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for item in results:
            child = child_dir / str(item["file_name"])
            zf.write(child, arcname=child.name)

    return {
        "input": str(input_path),
        "output_directory": str(run_dir),
        "summary": str(summary_path),
        "zip": str(zip_path),
        "detail_folder": str(child_dir),
        "source_rows": len(rows),
        "payment_departments": len(results),
        "daily_total": display_number(raw_daily),
        "night_total": display_number(raw_night),
        "travel_total": display_number(raw_travel),
        "payment_total": display_number(raw_daily + raw_night + raw_travel),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="按19个付款部门拆分月度补贴总表，并重新计算合计/元。")
    parser.add_argument("input", type=Path, help="输入的未加密 .xlsx 总表")
    parser.add_argument("-o", "--output", type=Path, default=Path("outputs"), help="输出目录，默认：outputs")
    args = parser.parse_args()
    result = split_payment_allowances(args.input.resolve(), args.output.resolve())
    print("拆分完成")
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
