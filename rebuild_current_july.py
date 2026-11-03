from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from split_payment_allowances import HEADERS, split_payment_allowances

ROOT = Path(r'I:\AI_Develop\py_AI')
WORK_DIR = ROOT / 'work'
OUTPUT_ROOT = ROOT / 'outputs'
SOURCE_FILE = WORK_DIR / '7月份补贴_源数据_无总计行.xlsx'

# 依据此前确认的7月份116条明细重建；原“合计/元”列按原误填值100保留，
# 正式拆分时由 split_payment_allowances.py 重新计算 G+H+I。
GROUPS = [
    ('老进化', '总经办', '总经办', '总经办', '葛亚曦'),
    ('深圳再造', '总经办', '总经办', '总经办', '赵嘉娜、周婷、吴积昊、滕思仪'),
    ('新进化', '发展中心', '发展中心', '发展中心', '李小柳、宋业云、罗漫婷、李娜、焦兰兰、刘培丽、赵静、孔赛男、刘灵、刘思桃'),
    ('深圳再造', '营销及品牌部', '营销及品牌部', '营销及品牌部', '张晔、董佳慧、刘婉如、王一荻、林腾、麦丽娜'),
    ('深圳再造', '供应链中心', '仓储物流部', '仓储物流部', '梁璐、万华思、刘胜勇'),
    ('深圳再造', '供应链中心', '质检组', '质检组', '莫光星'),
    ('深圳再造', '供应链中心', '采购部', '采购部', '刘敏、杜曼、黎梦华、权志伟'),
    ('深圳再造', '人力行政中心', '人力资源组', '人力资源组', '王正道、刘冬珍、单一锦、韦筱扬'),
    ('深圳再造', '人力行政中心', '薪酬绩效组', '薪酬绩效组', '宋迎超'),
    ('深圳再造', '人力行政中心', '行政管理组', '行政管理组', '刘琴、杨娘会、潘树雪莹、黄晓聪、李伟俊'),
    ('老进化', '人力行政中心', '行政管理组', '行政管理组', '于际稳、张雷'),
    ('上海再造', '人力行政中心', '上海中心', '上海中心', '李梦蓉'),
    ('深圳再造', '财务管理中心', '财务管理中心', '财务管理中心', '邹阿妮、李玲玲、张温谊、王子越、张瑶、张金逸、程宇、李冬荣'),
    ('新进化', '硬装事业部', '地产组', '地产组', '戴强涛'),
    ('新进化', '硬装事业部', '地产组', '设计A组', '张超、黄王贞、叶先超、杜耀飞、黄锦峰、张红岩、肖欣莲、林冰婷、陈坤、毛承峰、李勇、张宇杰、宋向茜、刘秀娟、吴玉玲、戴强、邓馨匀、林养娜、高征礼、赵海雯、周慧玲、窦嘉勤'),
    ('上海再造', '硬装事业部', '地产组', '上海组', '郭春廷、叶雨润、余晨、杨洪博、陈威铭'),
    ('新进化', '硬装事业部', '商业组', '商业组', '符宝、邓亦川、章子涵、梁治表'),
    ('新进化', '硬装事业部', '技术组', '技术组', '罗小博、黄文伟、王武林'),
    ('新进化', '硬装事业部', '技术组', '施工图组', '曾腾飞、谢健华、严远亮、许启恒、曾杰'),
    ('新进化', '硬装事业部', '技术组', '表现组', '梁思豪'),
    ('新进化', '硬装事业部', '技术组', '物料组', '陈准'),
    ('新进化', '软装事业部', '软装一部', '软装深圳B组', '邱瑞祺、张宝文、萧宝宝、赵凤鲜、陈昊'),
    ('新进化', '软装事业部', '软装一部', '软装深圳A组', '张筱、卢婕婷、胡家豪、周慧杰'),
    ('新进化', '软装事业部', '软装二部', '软装深圳C组', '聂婉怡、张一娟、于阳'),
    ('新进化', '软装事业部', '软装二部', '软装深圳D组', '张潘婷、张明霞、冯晓彤、张芷涵、王桐格、杨楠'),
    ('上海再造', '软装事业部', '软装二部', '软装上海组', '杨钧婷、赵钱钱、刘佳琦、师紫钦、刘科宇'),
    ('新进化', '软装事业部', '软装二部', '软装上海组', '林华龙'),
]


def create_source() -> int:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = '7月份补贴'
    ws.merge_cells('A1:K1')
    ws['A1'] = '7月份补贴'
    ws['A1'].fill = PatternFill('solid', fgColor='1F4E78')
    ws['A1'].font = Font(name='Microsoft YaHei', size=14, bold=True, color='FFFFFF')
    ws['A1'].alignment = Alignment(horizontal='center', vertical='center')
    ws.row_dimensions[1].height = 28
    for col, value in enumerate(HEADERS, start=1):
        c = ws.cell(2, col, value)
        c.fill = PatternFill('solid', fgColor='D9EAF7')
        c.font = Font(name='Microsoft YaHei', bold=True)
        c.alignment = Alignment(horizontal='center', vertical='center')
    side = Side(style='thin', color='B7C9D6')
    border = Border(left=side, right=side, top=side, bottom=side)
    serial = 1
    for company, first, second, third, names in GROUPS:
        for name in names.split('、'):
            values = [serial, company, name, first, second, third, 100, 100, 100, 100, None]
            for col, value in enumerate(values, start=1):
                cell = ws.cell(serial + 2, col, value)
                cell.border = border
                cell.font = Font(name='Microsoft YaHei', size=10)
                cell.alignment = Alignment(horizontal='right' if col in {7,8,9,10} else 'center', vertical='center')
                if col in {7,8,9,10}:
                    cell.number_format = '#,##0.00;[Red]-#,##0.00'
            serial += 1
    widths = [8,14,12,15,15,16,12,12,12,12,28]
    for col, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.freeze_panes = 'A3'
    ws.auto_filter.ref = f'A2:K{serial + 1}'
    wb.save(SOURCE_FILE)
    return serial - 1


if __name__ == '__main__':
    count = create_source()
    if count != 116:
        raise RuntimeError(f'源数据条数异常：{count}')
    result = split_payment_allowances(SOURCE_FILE, OUTPUT_ROOT)
    if result['payment_total'] != 34800:
        raise RuntimeError(f"付款总额异常：{result['payment_total']}")
    print('当前7月修正版生成完成')
    for key, value in result.items():
        print(f'{key}: {value}')
