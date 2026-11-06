# Agent Interview Server

基于 Python + FastAPI 的 AI 应用服务端。提供问候接口和 DeepSeek 非流式、流式问答接口。

## 环境要求

- Python 3.11 或以上版本

## 本地启动

在项目根目录执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

启动后可访问：

- Swagger 文档：http://127.0.0.1:8000/docs
- ReDoc 文档：http://127.0.0.1:8000/redoc
- OpenAPI 描述：http://127.0.0.1:8000/openapi.json

访问根路径 `/` 返回 404 属于预期行为。
`--reload` 仅用于本地开发。

## 项目结构

```text
app/
├── __init__.py
├── main.py             # 应用入口：创建应用、注册路由
├── config.py           # 配置：读取环境变量、集中管理模型参数
├── api/
│   ├── __init__.py
│   ├── hello.py        # 连通检查接口
│   ├── chat.py         # 原非流式问答接口、HTTP 错误转换
│   └── chat_stream.py  # 新增流式问答接口、SSE 事件编码
├── schemas/
│   ├── __init__.py
│   └── chat.py         # 请求和响应的数据模型
└── services/
    ├── __init__.py
    ├── deepseek.py     # 原非流式模型调用、响应解析、服务异常
    └── deepseek_stream.py  # 新增流式模型调用、文本增量与结束检查
pyproject.toml          # 项目元信息与依赖
README.md
```

## DeepSeek 问答（第一步）

确保启动服务的进程能够读取环境变量 `DEEPSEEK_API_KEY`。如果从 PyCharm
启动，需要在运行配置中提供该变量；终端中设置的变量不一定会被 IDE 继承。
不要将真实密钥写入代码、文档或 Git。

模型调用使用 OpenAI Python SDK（`openai>=2.0,<3.0`）的 `AsyncOpenAI`，
通过 DeepSeek 的兼容接口访问模型，仍使用 `DEEPSEEK_API_KEY`，无需 OpenAI 密钥。
SDK 自动重试已关闭。原 `POST /chat` 继续返回完整回答，新增 `POST /chat/stream` 提供流式输出。

本次新增 SDK 依赖，运行前需在项目虚拟环境中执行 `python -m pip install -e .`，然后启动服务。
在 `/docs` 页面展开 `POST /chat`，输入：

```json
{"message": "请用一句话解释 FastAPI 是什么"}
```

成功响应格式：

```json
{"answer": "模型返回的完整回答"}
```

每次请求独立，不保存对话历史。当前使用 `deepseek-flash`，显式关闭思考模式，
最多生成 2048 token。模型调用总时限为 60 秒，包含连接、发送与读取响应；
Android 客户端读取超时为 75 秒、完整请求超时为 90 秒，为后端返回超时错误留出余量。
空白问题或超过 10000 字符的问题返回 422；密钥未配置
返回 503；网络或上游服务错误返回 502；超时返回 504。错误响应使用 FastAPI
的 `detail` 字段，不透传上游原始错误。

请求按以下顺序处理：

`main.py` 注册路由 → `api/chat.py` 接收请求 → `schemas/chat.py` 校验数据
→ `services/deepseek.py` 通过异步 SDK 调用模型 → 路由返回 `ChatResponse`。

SDK 调用形式为 `await client.chat.completions.create(...)`，通过
`extra_body={"thinking": {"type": "disabled"}}` 传递 DeepSeek 扩展参数，
从 `response.choices[0].message.content` 读取完整回答。SDK 的超时、连接、
HTTP 状态及响应格式异常会转换为现有服务层异常，保持客户端接口与错误状态码不变。

`config.py` 通过 FastAPI 的 `Depends` 注入路由，再作为普通参数传给服务函数。
`Depends` 表示由 FastAPI 调用配置函数并提供结果。服务层不导入 FastAPI，
只抛出自己的异常；路由层决定对应的 HTTP 状态码。

建议依次阅读数据模型、配置、服务、路由，最后阅读入口。
Python 的说明注释放在模块、类或函数开头，使用三引号文档字符串；
普通代码说明使用 `#` 注释。
此接口目前仅供本地学习，尚未加入身份验证，请勿直接暴露到公网。

## DeepSeek 流式问答

新增 `POST /chat/stream`，与原 `POST /chat` 独立，复用相同请求校验：

```json
{"message": "请介绍一下 FastAPI"}
```

响应类型为 `text/event-stream`，采用 SSE 格式。每个事件以空行结束，
`data` 为 JSON，回答中的换行、引号等由 JSON 转义，不应按网络数据块直接拆事件。

```text
event: delta
data: {"text":"FastAPI"}

event: delta
data: {"text":" 是一个 Python Web 框架。"}

event: done
data: {}

```

- `delta`：`text` 是新增文本，客户端按顺序追加，不是完整回答。
- `done`：模型正常结束且已输出有效文本；此事件后流结束。
- `error`：生成失败、超时、输出达到上限或上游提前断流；保留已收到的文本，提示回答未完成，不再发送 `done`。
- 未收到 `done` 或 `error` 就断开，应视为传输中断，不能认为生成成功。

错误事件示例：

```text
event: error
data: {"message":"DeepSeek 流式响应超时，请稍后重试"}

```

请求参数不合法时返回 HTTP 422，密钥未配置时返回 HTTP 503；此时尚未开始 SSE。
开始 SSE 后 HTTP 状态为 200，上游连接、鉴权、余额和生成错误均通过 `error` 事件通知，
不能再通过 HTTP 502／504 表达，客户端必须解析终止事件。

流式接口继续使用 `deepseek-flash`、非思考模式和最多 2048 token，关闭自动重试。
流式生成总时限独立设为 180 秒；SDK 网络各阶段超时沿用配置的 60 秒，
读取超时限制等待下一批网络数据的时间，不是整个回答的生成时间。本接口暂不发送心跳。
流式读取被取消或发生异常时，通过上下文管理器关闭上游流和 SDK 客户端。
原非流式接口的代码、响应格式和 60 秒总时限均保持不变。

可在服务启动后手动使用以下命令查看逐段输出（`-N` 关闭 curl 输出缓冲）：

```bash
curl -N --request POST http://127.0.0.1:8000/chat/stream \
  --header 'Content-Type: application/json' \
  --data '{"message":"请介绍一下 FastAPI"}'
```

本次只新增后端能力，Android 仍使用原非流式接口。后续接入时需单独设置流式超时，
现有客户端 90 秒完整请求上限可能在流式生成结束前切断连接。
本次未执行启动、测试或模型调用，实际流式效果待手动确认。
