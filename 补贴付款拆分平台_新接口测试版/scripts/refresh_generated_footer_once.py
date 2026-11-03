"""Refresh this task's existing attachments without resetting task/personnel selections."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.splitter import generate_selected_payment_files
from openpyxl import load_workbook

TASK = '3e1b5ccd8e9d48c18d6decf80a82a0af'
TEXT = '付款金额＝日常餐补＋宵夜餐补＋出差餐补'
OUT = ROOT / 'output' / 'footer_refresh_20261013'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(old, new):
    a, b = load_workbook(old), load_workbook(new)
    assert a.sheetnames == b.sheetnames
    changes = []
    for name in a.sheetnames:
        x, y = a[name], b[name]
        assert (x.max_row, x.max_column, x.freeze_panes, x.auto_filter.ref) == (
            y.max_row, y.max_column, y.freeze_panes, y.auto_filter.ref)
        assert str(x.merged_cells) == str(y.merged_cells)
        assert len(x._images) == len(y._images) == 0 and len(x._charts) == len(y._charts) == 0
        for row in x:
            for old_cell in row:
                new_cell = y[old_cell.coordinate]
                if old_cell.value == TEXT:
                    assert old_cell.column == 11 and old_cell.row == x.max_row and new_cell.value is None
                    changes.append(old_cell.coordinate)
                else:
                    assert old_cell.value == new_cell.value, (old.name, old_cell.coordinate)
                assert old_cell._style == new_cell._style, (old.name, old_cell.coordinate, 'style')
        for key, dimension in x.column_dimensions.items():
            assert dimension.width == y.column_dimensions[key].width
        for key, dimension in x.row_dimensions.items():
            assert dimension.height == y.row_dimensions[key].height
    a.close()
    b.close()
    assert len(changes) == 1
    return changes


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / 'applied_guard.json').exists():
        raise RuntimeError('本批附件已经更新，请读取现有报告。')
    protected = [ROOT / '.env', ROOT / 'data/workflow.db', ROOT / 'app/dingtalk.py']
    before = {str(p): digest(p) for p in protected}
    db = sqlite3.connect((ROOT / 'data/workflow.db').as_uri() + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    try:
        record = dict(db.execute('select * from tasks where id=?', (TASK,)).fetchone())
        task = json.loads(record['data_json'])
        assert record['status'] == 'prepared' and task['result']['title'] == 'Lsd 9月份餐补'
        mappings = {(r['company'], r['source_department']): r['payment_department']
                    for r in db.execute('select * from department_mappings')}
    finally:
        db.close()
    old_result = task['result']
    generated = generate_selected_payment_files(Path(record['source_path']), OUT / 'staging', task['choices'], mappings)
    assert len(generated['departments']) == len(old_result['departments']) == 18
    old_groups = {g['id']: g for g in old_result['departments']}
    replacements = []
    checks = []
    for group in generated['departments']:
        old = old_groups[group['id']]
        assert {k: v for k, v in group.items() if k != 'file_path'} == {
            k: v for k, v in old.items() if k != 'file_path'}
        original, staged = Path(old['file_path']), Path(group['file_path'])
        checks.append({'file': original.name, 'cleared_cells': verify(original, staged)})
        replacements.append((original, staged))
    original_zip, staged_zip = Path(old_result['zip']), Path(generated['zip'])
    with zipfile.ZipFile(staged_zip) as archive:
        assert set(archive.namelist()) == {g['file_name'] for g in generated['departments']}
        for group in generated['departments']:
            assert archive.read(group['file_name']) == Path(group['file_path']).read_bytes()
    replacements.append((original_zip, staged_zip))
    assert all(digest(p) == before[str(p)] for p in protected)
    backup = OUT / 'backup'
    backup.mkdir(exist_ok=True)
    for original, staged in replacements:
        shutil.copy2(original, backup / original.name)
    with (OUT / 'applied_guard.json').open('x', encoding='utf-8') as stream:
        json.dump({'task': TASK, 'started_at': datetime.now().astimezone().isoformat()}, stream)
    for original, staged in replacements:
        temporary = original.with_name(original.name + '.footer-refresh.tmp')
        shutil.copy2(staged, temporary)
        temporary.replace(original)
        assert digest(original) == digest(staged)
    report = {'task': TASK, 'updated_workbooks': len(checks), 'updated_zip': str(original_zip),
              'only_footer_text_changed': True, 'cell_checks': checks,
              'task_env_and_dingtalk_unchanged': all(digest(p) == before[str(p)] for p in protected),
              'finished_at': datetime.now().astimezone().isoformat()}
    (OUT / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'cell_checks'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
