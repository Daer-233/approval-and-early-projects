# LOL BERT 意图识别 MCP 服务

这个项目用于训练一个 CPU 版 BERT 意图识别模型，并通过 MCP Server 暴露给 Dify 调用。

## 目录

- `data/intents_binary.csv`：二分类样例训练数据，格式为 `text,label`
- `lol_intent/train.py`：BERT 微调训练脚本
- `lol_intent/predictor.py`：本地预测封装
- `lol_intent/mcp_server.py`：MCP Server，给 Dify 调用
- `requirements-torch-cpu.txt`：CPU 版 PyTorch 依赖
- `requirements.txt`：Transformers、MCP、sklearn 等依赖

## 需要你提供的资料

上线前最好提供这些资料：

1. 真实用户问题语料：每个意图至少 50-200 条，越真实越好。
2. 意图标签表：标签英文名、中文含义、业务处理方式。
3. Dify 需要的返回格式：只要意图，还是要置信度、候选意图、槽位。
4. 是否需要槽位抽取：例如英雄名、位置、版本、段位、模式。
5. 运行方式：Dify 和这个 MCP 服务是否在同一台机器/同一个 Docker 网络。

当前只做二分类：

- `professional_question`：专业问题，和 LOL 玩法、英雄、出装、符文、对线、打野、团战、版本、战绩、客户端问题等相关
- `daily_question`：普通日常问题，寒暄、闲聊、生活常识、非 LOL 专业咨询、情绪表达等

## Conda 环境

当前项目推荐使用 conda 环境 `lol_bert311`。

```powershell
cd I:\AI_Develop\py_AI\lol_bert_intent
D:\software\anaconda3\Scripts\conda.exe activate lol_bert311
```

如果需要重新创建环境：

```powershell
D:\software\anaconda3\Scripts\conda.exe create -y -n lol_bert311 python=3.11 pip
D:\software\anaconda3\Scripts\conda.exe run -n lol_bert311 python -m pip install -r requirements-torch-cpu.txt
D:\software\anaconda3\Scripts\conda.exe run -n lol_bert311 python -m pip install -r requirements.txt
```

## 训练

第一次训练会下载 `bert-base-chinese`，需要能访问 HuggingFace。

直接运行：
```bash
python run_train.py
```

或者手动指定参数：
```powershell
C:\Users\liwj\.conda\envs\lol_bert311\python.exe -m lol_intent.train --data data\intents_binary.csv --epochs 5 --batch-size 8
```

训练结果会保存到：

```text
models/lol-bert-binary-intent
```

## 本地预测

```powershell
C:\Users\liwj\.conda\envs\lol_bert311\python.exe -m lol_intent.cli_predict "亚索怎么打劫"
```

返回示例：

```json
{
  "text": "亚索怎么打劫",
  "intent": "professional_question",
  "description": "专业问题：和LOL玩法、英雄、出装、符文、对线、打野、团战、版本、战绩、客户端问题等相关",
  "confidence": 0.91,
  "candidates": []
}
```

## 启动 MCP Server 给 Dify 调用

直接运行：
```bash
python run_mcp.py
```

或者手动启动：
```powershell
$env:LOL_INTENT_MODEL_DIR="models/lol-bert-binary-intent"
$env:MCP_HOST="0.0.0.0"
$env:MCP_PORT="8008"
C:\Users\liwj\.conda\envs\lol_bert311\python.exe -m lol_intent.mcp_server --transport sse
```

然后在 Dify：

1. 进入 `Tools -> MCP`
2. 选择 `Add MCP Server (HTTP)`
3. Server URL 填这个服务地址，通常是：

```text
http://你的机器IP:8008/sse
```

如果 Dify 和服务在同一台机器，本地测试可以用：

```text
http://127.0.0.1:8008/sse
```

Dify 文档目前说明 MCP 工具通过 `Tools -> MCP -> Add MCP Server (HTTP)` 添加，并会自动发现服务暴露的 tools。

也可以使用 MCP SDK 推荐的 Streamable HTTP：

```bash
python run_mcp.py streamable
```

对应地址通常是：

```text
http://你的机器IP:8008/mcp
```

如果 Dify 连接 `/mcp` 报 `503 Service Unavailable`，可以改用 SSE：

```bash
python run_mcp.py
```

Dify 地址填：

```text
http://你的机器IP:8008/sse
```

## MCP 暴露的工具

- `classify_lol_intent(text, top_k=3)`：识别 LOL 用户问题意图
- `list_lol_intents()`：查看当前支持的意图标签

## 数据格式

CSV 必须包含：

```csv
text,label
亚索怎么出装,professional_question
你好,daily_question
```

标签建议使用英文小写和下划线，方便 Dify 工作流判断。
