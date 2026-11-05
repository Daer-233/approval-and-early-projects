# FlowSplit · 补贴付款拆分工作台

这是一个面向月度餐补付款准备的前后端网站 MVP。它把现有的 Excel 拆分逻辑封装成同域 Web 服务：上传一份 `.xlsx` 总表，系统自动按 19 个付款部门归集，重新计算三类餐补，生成带总计行的新汇总表、19 份子表和 ZIP 压缩包。

## 主要能力

- React 响应式工作台，适配电脑和手机；
- FastAPI + openpyxl 后端，实际读取并生成 Excel；
- 19 条付款部门规则已写入规则中心；
- 金额严格按 `日常餐补 + 宵夜餐补 + 出差餐补` 重新计算，不读取原表的合计列；
- 自动跳过原表总计/合计行；新汇总表会补回总计行；人数按整数展示；
- 支持下载 19 份子表 ZIP、带总计行汇总表、单份部门子表；
- Nginx 将 `/` 和 `/api/` 放在同一个域名下，无需额外跨域配置。

> 请只上传你有权处理的、未加密且可编辑的 `.xlsx` 文件。系统不绕过公司加密、WPS 文档权限或密码保护。

## 本地开发

### 1. 启动后端

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001
```

### 2. 启动前端

```powershell
cd frontend
npm install
npm run dev
```

打开 Vite 输出的地址（通常是 `http://localhost:5173`）。开发服务器会把 `/api` 转发到 `8001`。

### 3. 一键部署（Docker + Nginx）

```powershell
docker compose up -d --build
```

浏览器访问部署机器的域名或 IP。正式环境只需要把 Nginx `server_name _;` 改为你的域名，并在外层配置 HTTPS 证书。

## 后续扩展建议

一期使用本地卷和内存任务状态，适合单机内部使用。接入正式钉钉前建议增加：登录/钉钉免登、SQLite/PostgreSQL 任务记录、Redis/Celery 异步队列、对象存储、操作日志和规则管理员权限。

## 开源依赖与来源

### 实际使用

- [FastAPI](https://github.com/fastapi/fastapi)：提供后端 HTTP API。
- [Uvicorn](https://github.com/encode/uvicorn)：运行 ASGI 服务。
- [python-multipart](https://github.com/Kludex/python-multipart)：处理表单文件上传。
- [openpyxl](https://pypi.org/project/openpyxl/)：读取 Excel 工作簿并生成拆分结果。
- [React / React DOM](https://github.com/facebook/react)：渲染 Web 界面。
- [Vite](https://github.com/vitejs/vite)：本地开发与前端构建。
- [Docker Compose](https://github.com/docker/compose)：启动前后端容器。
- [Nginx](https://github.com/nginx/nginx)：同源提供页面和 API 代理。
- [Node.js](https://github.com/nodejs/node)：在构建镜像中运行 Vite。
- [Python](https://github.com/python/cpython)：在后端镜像中运行应用。
