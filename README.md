# 审批工具与早期原型

- [补贴付款拆分平台](AI_PJ/补贴付款拆分平台/README.md) · 按部门拆分表格的 Web 工具，包含 Docker 部署配置。
- [BERT 意图识别](lol_bert_intent/README.md) · 训练分类器并通过 MCP 提供推理工具。
- [Ant Design 界面重建](codex_antd_rebuild/) · 审批工具的前端原型。
- [AutoCAD COM 绘图说明](AUTOCAD_COM_绘图说明书.md) · Windows 上的绘图自动化示例。
- [局域网版](补贴付款拆分平台_局域网版/) 与 [新接口测试版](补贴付款拆分平台_新接口测试版/) · 早期审批实验。

## 开源依赖与来源

### 实际使用

- [Ant Design](https://github.com/ant-design/ant-design)：提供管理界面的组件。
- [Ant Design Icons](https://github.com/ant-design/ant-design-icons)：提供界面图标。
- [React / React DOM](https://github.com/facebook/react)：渲染 Web 界面。
- [Vite](https://github.com/vitejs/vite)：本地开发与前端构建。
- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react)：为 Vite 提供 React 编译支持。
- [FastAPI](https://github.com/fastapi/fastapi)：提供后端 HTTP API。
- [Uvicorn](https://github.com/encode/uvicorn)：运行 ASGI 服务。
- [python-multipart](https://github.com/Kludex/python-multipart)：处理表单文件上传。
- [openpyxl](https://pypi.org/project/openpyxl/)：读取 Excel 工作簿并生成拆分结果。
- [odfpy](https://github.com/eea/odfpy)：读取 OpenDocument 表格。
- [numbers-parser](https://pypi.org/project/numbers-parser/)：读取 Apple Numbers 表格。
- [pywin32](https://github.com/mhammond/pywin32)：调用 Windows COM 和自动化接口。
- [HTTPX](https://github.com/encode/httpx)：发起 HTTP 请求及测试接口。
- [python-dotenv](https://github.com/theskumar/python-dotenv)：加载本地环境文件。
- [Dify](https://github.com/langgenius/dify)：提供早期聊天页面的集成对象。
