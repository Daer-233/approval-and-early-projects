import math
import os
import sys
import pythoncom
import win32com.client
from win32com.client import VARIANT
from array import array


def V3(x, y, z=0.0):
    return VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8,
                   array("d", [float(x), float(y), float(z)]))


def V2_flat(points):
    flat = array("d")
    for p in points:
        flat.extend([float(p[0]), float(p[1])])
    return VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, flat)


class CadDraw:
    def __init__(self):
        # 尝试连接已运行的 AutoCAD，否则启动新实例
        try:
            self.app = win32com.client.GetActiveObject("AutoCAD.Application")
            print("已连接到正在运行的 AutoCAD")
        except:
            print("未检测到 AutoCAD 实例，尝试启动...")
            try:
                self.app = win32com.client.Dispatch("AutoCAD.Application")
            except:
                raise RuntimeError(
                    "无法启动 AutoCAD，请确认已安装 AutoCAD 且版本支持 COM 自动化"
                )
        self.app.Visible = True
        self.doc = self.app.Documents.Add("acadiso.dwt")
        self.ms = self.doc.ModelSpace

    def add_layer(self, name, color):
        lay = self.doc.Layers.Add(name)
        lay.Color = color

    def line(self, x1, y1, x2, y2, layer=None):
        obj = self.ms.AddLine(V3(x1, y1), V3(x2, y2))
        if layer:
            obj.Layer = layer
        return obj

    def rect(self, x1, y1, x2, y2, layer=None):
        pts = [(x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)]
        pl = self.ms.AddLightWeightPolyline(V2_flat(pts))
        pl.Closed = True
        if layer:
            pl.Layer = layer
        return pl

    def text(self, s, x, y, h=0.35, layer=None):
        obj = self.ms.AddText(s, V3(x, y), h)
        if layer:
            obj.Layer = layer
        return obj

    def door_left(self, y_center, layer=None):
        """走廊左墙(x=13)的门，向左开进房间"""
        hx, hy, w = 13, y_center - 0.45, 0.9
        ln = self.ms.AddLine(V3(hx, hy), V3(hx - w, hy))
        arc = self.ms.AddArc(V3(hx, hy), w, math.pi / 2, math.pi)
        if layer:
            ln.Layer = layer
            arc.Layer = layer

    def door_right(self, y_center, layer=None):
        """走廊右墙(x=15)的门，向右开进房间"""
        hx, hy, w = 15, y_center - 0.45, 0.9
        ln = self.ms.AddLine(V3(hx, hy), V3(hx + w, hy))
        arc = self.ms.AddArc(V3(hx, hy), w, 0, math.pi / 2)
        if layer:
            ln.Layer = layer
            arc.Layer = layer

    def door_inner_right(self, x, y_center, layer=None):
        """内墙(x)的门，向右开"""
        hx, hy, w = x, y_center - 0.45, 0.9
        ln = self.ms.AddLine(V3(hx, hy), V3(hx + w, hy))
        arc = self.ms.AddArc(V3(hx, hy), w, 0, math.pi / 2)
        if layer:
            ln.Layer = layer
            arc.Layer = layer

    def door_entrance_left(self, layer=None):
        """入口左门 hinge(13,0) 向上开"""
        hx, hy, w = 13, 0, 1.0
        ln = self.ms.AddLine(V3(hx, hy), V3(hx, hy + w))
        arc = self.ms.AddArc(V3(hx, hy), w, 0, math.pi / 2)
        if layer:
            ln.Layer = layer
            arc.Layer = layer

    def door_entrance_right(self, layer=None):
        """入口右门 hinge(15,0) 向上开"""
        hx, hy, w = 15, 0, 1.0
        ln = self.ms.AddLine(V3(hx, hy), V3(hx, hy + w))
        arc = self.ms.AddArc(V3(hx, hy), w, math.pi / 2, math.pi)
        if layer:
            ln.Layer = layer
            arc.Layer = layer

    def save(self, path):
        self.doc.SaveAs(path)
        print(f"图纸已保存: {path}")

    def zoom_extents(self):
        self.doc.SendCommand("ZOOM\nE\n")


def main():
    draw = CadDraw()
    draw.add_layer("墙体", 7)
    draw.add_layer("门窗", 2)
    draw.add_layer("家具", 3)
    draw.add_layer("文字", 4)

    W, D, F, T = "墙体", "门窗", "家具", "文字"

    # ======== 1. 建筑外轮廓 (入口留空) ========
    draw.line(0, 0, 13, 0, W)
    draw.line(15, 0, 28, 0, W)
    draw.line(28, 0, 28, 18, W)
    draw.line(28, 18, 0, 18, W)
    draw.line(0, 18, 0, 0, W)

    # ======== 2. 走廊 (x=13~15 共2m宽) ========
    draw.line(13, 0, 13, 18, W)
    draw.line(15, 0, 15, 18, W)

    # ======== 3. 左侧房间 ========
    draw.rect(0.5, 0.5, 12.5, 5.5, W)    # 会议室
    draw.rect(0.5, 6, 12.5, 12, W)        # 开放办公区
    draw.rect(0.5, 12.5, 12.5, 17.5, W)   # 前台

    # ======== 4. 右侧房间 ========
    draw.rect(15.5, 0.5, 22, 5.5, W)       # 办公室A
    draw.rect(22.5, 0.5, 27.5, 5.5, W)     # 办公室B
    draw.rect(15.5, 6, 22, 12, W)           # 办公室C
    draw.rect(22.5, 6, 27.5, 12, W)         # 办公室D
    draw.rect(15.5, 12.5, 22, 15, W)        # 茶水间
    draw.rect(22.5, 12.5, 27.5, 15, W)      # 储藏室
    draw.rect(15.5, 15.5, 22, 17.5, W)      # 卫生间(女)
    draw.rect(22.5, 15.5, 27.5, 17.5, W)    # 卫生间(男)

    # ======== 5. 门 ========
    draw.door_entrance_left(D)
    draw.door_entrance_right(D)

    draw.door_left(3.0, D)      # 会议室
    draw.door_left(9.0, D)      # 开放办公区
    draw.door_left(15.0, D)     # 前台

    draw.door_right(3.0, D)     # 办公室A
    draw.door_right(9.0, D)     # 办公室C
    draw.door_right(13.7, D)    # 茶水间
    draw.door_right(16.5, D)    # 卫生间女

    # 右侧内部门 (从内墙22.5向右开)
    for cy in [3.0, 9.0, 13.7, 16.5]:
        draw.door_inner_right(22.5, cy, D)

    # ======== 6. 文字标注 ========
    draw.text("会议室", 4, 2.5, 0.5, T)
    draw.text("开放办公区", 3, 8.5, 0.5, T)
    draw.text("前台接待", 4, 14.5, 0.5, T)
    draw.text("办公室 A", 16.5, 2.5, 0.35, T)
    draw.text("办公室 B", 23.5, 2.5, 0.35, T)
    draw.text("办公室 C", 16.5, 8.5, 0.35, T)
    draw.text("办公室 D", 23.5, 8.5, 0.35, T)
    draw.text("茶水间", 17, 13.3, 0.35, T)
    draw.text("储藏室", 24, 13.3, 0.35, T)
    draw.text("卫生间(女)", 16.5, 16.2, 0.3, T)
    draw.text("卫生间(男)", 23.5, 16.2, 0.3, T)
    draw.text("走廊", 13.5, 8.5, 0.35, T)

    # ======== 7. 简易家具 ========
    # 会议室: 会议桌 + 椅子
    draw.rect(4, 1.5, 9, 4.5, F)
    for cx in [4.5, 6.5, 8.5]:
        for cy in [1.2, 4.8]:
            draw.ms.AddCircle(V3(cx, cy), 0.25).Layer = F

    # 前台接待台
    draw.rect(3, 13, 7, 15, F)

    # 开放办公区: 6个工位 (2行x3列)
    for row in range(2):
        for col in range(3):
            bx = 1.5 + col * 3.5
            by = 6.8 + row * 2.5
            draw.rect(bx, by, bx + 1.5, by + 1.2, F)

    # 办公室桌椅
    for ox, oy in [(16.5, 2.5), (23.5, 2.5), (16.5, 8.5), (23.5, 8.5)]:
        draw.rect(ox, oy, ox + 1.2, oy + 0.8, F)

    # 茶水间吧台
    draw.rect(16, 14, 21.5, 14.6, F)

    # ======== 8. 保存 + 全图缩放 ========
    dwg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "公司平面图.dwg")
    draw.save(dwg_path)
    draw.zoom_extents()
    print("✅ 公司平面图绘制完成！")


if __name__ == "__main__":
    main()
