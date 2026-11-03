import math, sys
import pythoncom
import win32com.client
from win32com.client import VARIANT
from array import array

def V3(x, y, z=0.0):
    return VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8,
                   array("d", [float(x), float(y), float(z)]))

def main():
    try:
        app = win32com.client.GetActiveObject("AutoCAD.Application")
        print("已连接 AutoCAD")
    except:
        print("启动 AutoCAD ...")
        sys.stdout.flush()
        app = win32com.client.Dispatch("AutoCAD.Application")
    app.Visible = True
    doc = app.Documents.Add("acadiso.dwt")
    ms = doc.ModelSpace

    doc.Layers.Add("轮廓").Color = 7
    doc.Layers.Add("纹理").Color = 4

    cx, cy, R = 100, 100, 50

    # ── 球体 ──
    ms.AddCircle(V3(cx, cy), R).Layer = "轮廓"

    # ── 水平主缝线 (∩形, 经过球心, 两端在球面) ──
    # 弧心(cx, cy-45), R=45, 22.5°~157.5°
    a = ms.AddArc(V3(cx, cy - 45), 45,
                  math.radians(22.5), math.radians(157.5))
    a.Layer = "纹理"

    # ── 垂直缝线 (与水平弧在球心交汇) ──
    ln = ms.AddLine(V3(cx, cy + R), V3(cx, cy - R))
    ln.Layer = "纹理"

    # ── 两侧副缝 (8片面板边界弧, 精准限角确保不超球面) ──
    a2 = ms.AddArc(V3(cx + 42, cy - 20), 22,
                   math.radians(155), math.radians(240))
    a2.Layer = "纹理"

    a3 = ms.AddArc(V3(cx - 42, cy - 20), 22,
                   math.radians(300), math.radians(25))
    a3.Layer = "纹理"

    doc.SendCommand("ZOOM\nE\n")
    print("篮球绘制完成!")

main()
