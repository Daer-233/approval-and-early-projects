# AutoCAD COM 自动绘图 — 给另一台 Codex 的说明书

## 一句话本质

AutoCAD COM 不接受 Python 普通的 `(x, y, z)` 元组作为坐标参数，必须用 `VARIANT` 包装的 double 数组。

```python
from win32com.client import VARIANT
from array import array
import pythoncom

def V3(x, y, z=0.0):
    return VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8,
                   array('d', [float(x), float(y), float(z)]))
```

**所有带坐标的 COM 方法，参数先过 `V3()`。** 这是唯一一定会踩的坑。

---

## 环境

```powershell
pip install pywin32
python -c "import win32com.client; print('ok')"
```

本机需要已安装 AutoCAD（任何版本）。

---

## 可用 API 速查

```python
# 连接 / 新建图纸
app = win32com.client.GetActiveObject("AutoCAD.Application")
doc = app.Documents.Add("acadiso.dwt")
ms = doc.ModelSpace

# 图层
lay = doc.Layers.Add("图层名")
lay.Color = 7   # 1=红 2=黄 3=绿 4=青 5=蓝 6=品红 7=白 8=灰

# 画图（所有坐标用 V3 包裹）
ms.AddLine(V3(x1,y1), V3(x2,y2))
ms.AddCircle(V3(cx,cy), radius)
ms.AddArc(V3(cx,cy), radius, startAngle, endAngle)   # 注意：圆心是一个点，不是三个数
ms.AddText("文字", V3(x,y), height)
ms.AddDimAligned(V3(x1,y1), V3(x2,y2), V3(x3,y3))

# 轻量多段线
from array import array
flat = array('d', [x1, y1, x2, y2, x3, y3, ...])
var = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, flat)
pline = ms.AddLightWeightPolyline(var)
pline.Closed = True

# 设置图层
line.Layer = "图层名"

# 缩放显示
doc.SendCommand("ZOOM\nE\n")
```

---

## 常见错误

| 报错 | 原因 | 修法 |
|------|------|------|
| `E_INVALIDARG` / `-2147024809` | 普通 tuple 传给了 COM 方法 | 改用 `V3()` |
| `AddArc() takes 1 to 5 arguments` | 圆心拆成三个数传进去了 | 改 `AddArc(V3(cx,cy), r, sa, ea)` |
| `AddLightWeightPolyline` 报错 | 传了 list 而不是 SAFEARRAY | 用 `array('d', ...)` + `VARIANT` 包装 |
| 中文文件名乱码 | PowerShell 编码问题 | 脚本文件用英文名 |

---

## 生产建议

- 定义 `V3()` 和 `VA2()` 辅助函数，所有坐标绘制都走它们
- `AddLine` 可以再包一层 `add_line(ms, x1, y1, x2, y2, layer)` 省掉重复写 `V3`
- 对应 `add_circle`、`add_rect`、`add_text` 同理
- 脚本文件用英文名保存，避免 PowerShell 传参时编码乱掉

---

## 运行方式

```powershell
python 脚本文件名.py
```

AutoCAD 可以提前打开，也可以让脚本自动启动。画完自动 `ZOOM E` 全图缩放。
