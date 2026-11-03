import win32com.client
import pythoncom
import math
from win32com.client import VARIANT
from array import array


# ============================================================
# 在 AutoCAD 中绘制客服中心平面图（通过 COM）
# 单位：毫米 (mm)
# ============================================================

def V3(x, y, z=0.0):
    """创建 3D 点 VARIANT（用于点参数）。"""
    return VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, array('d', [float(x), float(y), float(z)]))


def VA2(points):
    """创建轻量多段线顶点 VARIANT。points: [(x1,y1), (x2,y2), ...]"""
    flat = array('d', [float(v) for p in points for v in p])
    return VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, flat)


def connect_autocad():
    """连接到已打开的 AutoCAD，或启动新实例。"""
    pythoncom.CoInitialize()
    try:
        app = win32com.client.GetActiveObject("AutoCAD.Application")
        print("已连接到正在运行的 AutoCAD")
    except:
        app = win32com.client.Dispatch("AutoCAD.Application")
        app.Visible = True
        print("已启动新的 AutoCAD 实例")
    return app


def new_drawing(app):
    """创建新图纸。"""
    doc = app.Documents.Add("acadiso.dwt")
    doc.Activate()
    return doc


def setup_layers(doc):
    """设置图层。"""
    layers = doc.Layers
    layer_defs = [
        ("墙体", 7),
        ("门窗", 3),
        ("家具", 2),
        ("标注", 1),
        ("文字", 5),
        ("轴线", 8),
        ("填充", 6),
        ("设备", 4),
    ]
    for name, color in layer_defs:
        try:
            l = layers.Add(name)
            l.Color = color
        except:
            pass


def add_line(ms, x1, y1, x2, y2, layer):
    line = ms.AddLine(V3(x1, y1), V3(x2, y2))
    line.Layer = layer
    return line


def add_circle(ms, x, y, r, layer):
    c = ms.AddCircle(V3(x, y), float(r))
    c.Layer = layer
    return c


def add_text(ms, text, x, y, height, layer, align=0):
    """align: 0=Left, 1=Center"""
    t = ms.AddText(text, V3(x, y), float(height))
    t.Layer = layer
    if align == 1:
        t.Alignment = 4  # acAlignmentCenter
        t.TextAlignmentPoint = V3(x, y)
    return t


def add_rectangle(ms, x1, y1, x2, y2, layer):
    """用轻量多段线绘制矩形。"""
    pts = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
    pline = ms.AddLightWeightPolyline(VA2(pts))
    pline.Layer = layer
    pline.Closed = True
    return pline


def draw_door(ms, x, y, width, direction, layer):
    """
    绘制门：门扇弧 + 门线。
    direction: 'up' / 'down' / 'left' / 'right'
    """
    if direction == 'up':
        p1, p2 = (x, y), (x + width, y)
        cx, cy = x + width, y
        sa, ea = math.pi, 1.5 * math.pi
    elif direction == 'down':
        p1, p2 = (x, y), (x + width, y)
        cx, cy = x, y
        sa, ea = 0.5 * math.pi, math.pi
    elif direction == 'left':
        p1, p2 = (x, y), (x, y - width)
        cx, cy = x, y - width
        sa, ea = 0, 0.5 * math.pi
    elif direction == 'right':
        p1, p2 = (x, y), (x, y + width)
        cx, cy = x + width, y + width
        sa, ea = math.pi, 1.5 * math.pi
    else:
        return None

    add_line(ms, *p1, *p2, layer)
    # AddArc(centerX, centerY, centerZ, radius, startAngle, endAngle)
    arc = ms.AddArc(V3(cx, cy), float(width), -sa, -ea)
    arc.Layer = layer
    return arc


def draw_window(ms, x1, y1, x2, y2, layer):
    """绘制窗户：双线 + 中间竖线。"""
    add_line(ms, x1, y1, x2, y2, layer)
    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy)
    if length == 0:
        return
    nx = -dy / length * 80
    ny = dx / length * 80
    ox1, oy1 = x1 + nx, y1 + ny
    ox2, oy2 = x2 + nx, y2 + ny
    add_line(ms, ox1, oy1, ox2, oy2, layer)
    # 中间竖线
    for i in range(1, 4):
        t = i / 4
        mx = x1 + (x2 - x1) * t
        my = y1 + (y2 - y1) * t
        add_line(ms, mx, my, mx + nx, my + ny, layer)


def draw_desk(ms, x, y, w, d, layer):
    add_rectangle(ms, x, y, x + w, y + d, layer)


def draw_chair(ms, x, y, size, layer):
    add_circle(ms, x, y, size, layer)


def draw_sofa(ms, x, y, w, d, layer):
    add_rectangle(ms, x, y, x + w, y + d, layer)
    add_line(ms, x + 50, y + 50, x + w - 50, y + d - 50, layer)


def add_dim(ms, x1, y1, x2, y2, offset, layer):
    """添加对齐标注。"""
    dim = ms.AddDimAligned(V3(x1, y1), V3(x2, y2), V3(x1, y1 + offset))
    dim.Layer = layer
    return dim


def draw_customer_service_plan():
    """主函数：绘制客服中心平面图。"""
    app = connect_autocad()
    doc = new_drawing(app)
    ms = doc.ModelSpace

    setup_layers(doc)

    L_wall = "墙体"
    L_door = "门窗"
    L_furn = "家具"
    L_dim = "标注"
    L_text = "文字"

    X0, Y0, X1, Y1 = 0, 0, 14000, 11000

    # ============== 外轮廓 ==============
    add_rectangle(ms, X0, Y0, X1, Y1, L_wall)

    # ============== 内部分隔 ==============
    # 经理办公室：左下
    add_rectangle(ms, 200, 200, 4200, 4200, L_wall)
    # 会议室：右下
    add_rectangle(ms, 9600, 200, 13600, 4200, L_wall)
    # 茶水间 + 档案室：左上
    add_line(ms, 200, 7200, 4200, 7200, L_wall)
    add_line(ms, 4200, 7200, 4200, 10600, L_wall)
    # 分隔茶水间和档案室
    add_line(ms, 2200, 7200, 2200, 10600, L_wall)

    # ============== 门 ==============
    draw_door(ms, 4200, 1800, 900, 'up', L_door)    # 经理室
    draw_door(ms, 9600, 1800, 900, 'up', L_door)     # 会议室
    draw_door(ms, 800, 7200, 900, 'down', L_door)    # 茶水间
    draw_door(ms, 2500, 7200, 900, 'down', L_door)   # 档案室
    draw_door(ms, 5600, 0, 1500, 'down', L_door)     # 大门
    draw_door(ms, 7250, 0, 1500, 'down', L_door)     # 大门

    # ============== 窗户 ==============
    draw_window(ms, 4600, 11000, 9200, 11000, L_door)
    draw_window(ms, 14000, 4600, 14000, 8400, L_door)
    draw_window(ms, 0, 4600, 0, 8400, L_door)

    # ============== 家具 ==============
    # --- 前台接待柜台 ---
    add_rectangle(ms, 4800, 4800, 8400, 5600, L_furn)
    add_text(ms, "接待前台", 6600, 5200, 250, L_text, align=1)

    # --- 客服工位区 2排x3列 ---
    dw, dd, gx, gy = 1400, 1400, 300, 400
    sx, sy = 5000, 6000
    for row in range(2):
        for col in range(3):
            dx = sx + col * (dw + gx)
            dy = sy + row * (dd + gy)
            draw_desk(ms, dx, dy, dw, dd, L_furn)
            chx, chy = dx + dw / 2, (dy + dd + 200) if row == 0 else (dy - 200)
            draw_chair(ms, chx, chy, 200, L_furn)
            add_text(ms, f"工位{row*3+col+1}", dx + dw/2, dy + dd/2, 180, L_text, align=1)

    # --- 经理办公室 ---
    draw_desk(ms, 500, 500, 1600, 800, L_furn)
    draw_chair(ms, 1300, 500, 250, L_furn)
    add_rectangle(ms, 500, 1000, 800, 1400, L_furn)
    add_text(ms, "文件柜", 650, 1200, 150, L_text, align=1)
    add_rectangle(ms, 2600, 500, 3800, 1200, L_furn)
    draw_chair(ms, 3200, 450, 200, L_furn)
    draw_chair(ms, 3200, 1400, 200, L_furn)
    add_text(ms, "经理办公室", 2200, 3600, 250, L_text, align=1)

    # --- 会议室 ---
    add_rectangle(ms, 10200, 800, 13000, 2400, L_furn)
    for i in range(6):
        a = math.pi * i / 3
        draw_chair(ms, 11600 + 1200 * math.cos(a), 1600 + 1200 * math.sin(a), 180, L_furn)
    add_text(ms, "会议室", 11600, 3600, 250, L_text, align=1)

    # --- 茶水间 ---
    add_rectangle(ms, 500, 7600, 1800, 8000, L_furn)
    add_rectangle(ms, 500, 8800, 1800, 10000, L_furn)
    add_circle(ms, 1350, 8200, 250, L_furn)
    draw_chair(ms, 1350, 7900, 180, L_furn)
    draw_chair(ms, 1350, 8500, 180, L_furn)
    add_text(ms, "茶水间", 1200, 9800, 200, L_text, align=1)

    # --- 档案室 ---
    add_rectangle(ms, 2600, 7800, 3800, 9400, L_furn)
    add_rectangle(ms, 2600, 9600, 2800, 10200, L_furn)
    add_text(ms, "档案室", 3200, 9800, 200, L_text, align=1)

    # --- 等候区沙发 ---
    for i in range(3):
        s_x = 9200 + i * 1400
        draw_sofa(ms, s_x, 4000, 1200, 500, L_furn)
    add_text(ms, "等候区", 10700, 4700, 200, L_text, align=1)

    # --- 绿植 ---
    add_circle(ms, 7000, 3500, 300, "设备")
    add_circle(ms, 9100, 5200, 250, "设备")
    add_circle(ms, 7000, 5500, 300, "设备")

    # ============== 尺寸标注 ==============
    add_dim(ms, X0, Y0, X1, Y0, -1200, L_dim)
    add_dim(ms, X1, Y0, X1, Y1, 1200, L_dim)
    add_dim(ms, 200, 200, 4200, 200, -600, L_dim)
    add_dim(ms, 200, 200, 200, 4200, -600, L_dim)
    add_dim(ms, 9600, 200, 13600, 200, -600, L_dim)

    # ============== 图名 ==============
    add_text(ms, "客服中心平面布置图  比例 1:100", 7000, -2200, 500, L_text, align=1)

    # ============== 图例 ==============
    lx, ly = 200, -3800
    add_rectangle(ms, lx, ly, lx + 4000, ly + 1800, L_wall)
    add_text(ms, "图例", lx + 2000, ly + 1500, 300, L_text, align=1)
    items = [
        ("墙体", "墙体 / 隔墙"),
        ("门窗", "门 / 窗"),
        ("家具", "家具 / 设备"),
        ("标注", "尺寸标注"),
    ]
    for i, (lay, desc) in enumerate(items):
        y = ly + 1100 - i * 250
        add_line(ms, lx + 200, y, lx + 600, y, lay)
        add_text(ms, desc, lx + 700, y - 80, 180, L_text)

    # ============== 全图缩放 ==============
    doc.SendCommand("ZOOM\nE\n")

    print("✓ 客服中心平面图绘制完成！")
    return doc


if __name__ == "__main__":
    draw_customer_service_plan()
