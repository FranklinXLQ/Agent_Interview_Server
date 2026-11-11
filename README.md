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
│   ├── chat_stream.py  # 会话流式接口、HTTP 错误与 SSE 编码
│   ├── chat_stream_response.py  # 断开监听、生成器关闭和请求释放
│   └── dependencies.py # 应用级对话服务依赖
├── schemas/
│   ├── __init__.py
│   ├── chat.py         # 原非流式请求和响应
│   └── chat_stream.py  # 流式请求：message + session_id
├── errors/             # 跨层使用的会话业务异常
├── models/             # 独立文件定义完整问答、会话与请求快照
├── settings/           # 会话历史大小、过期与容量策略
├── storage/            # 内存会话存储
├── lifespan.py         # 应用级存储创建和定时清理
└── services/
    ├── __init__.py
    ├── deepseek.py     # 原非流式模型调用、响应解析、服务异常
    ├── deepseek_stream.py  # 消息列表调用、增量与正常结束检查
    └── conversation.py # 历史组装、回答累积和成功提交
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

`POST /chat/stream` 支持多轮上下文，与原 `POST /chat` 独立。
当前接口要求合法 UUID 形式的 `session_id`，同一段聊天每轮使用相同标识：

```json
{"message": "请介绍一下 FastAPI", "session_id": "e42122f5-bcd1-4808-bf26-53739d4c4299"}
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
- `done`：模型正常结束、有效回答已与本次问题成对保存；此事件后流结束。
- `error`：生成失败、超时、输出达到上限或上游提前断流；保留已收到的文本，提示回答未完成，不再发送 `done`。
- 未收到 `done` 或 `error` 就断开，应视为传输中断，不能认为生成成功。

错误事件示例：

```text
event: error
data: {"message":"DeepSeek 流式响应超时，请稍后重试"}

```

问题或 session_id 不合法时返回 HTTP 422；同一会话已有请求生成时返回 HTTP 409；
密钥未配置或会话容量已满时返回 HTTP 503。以上错误都发生在 SSE 开始前。
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
  --data '{"message":"请介绍一下 FastAPI","session_id":"e42122f5-bcd1-4808-bf26-53739d4c4299"}'
```

## 多轮对话策略

调用顺序：路由校验并占用会话 → 读取历史快照 → 历史 + 当前问题交给模型
→ 边发送 delta 边累积回答 → 正常结束后整轮保存 → 发送 done。

- 客户端只发当前问题和 session_id，历史由服务端管理；新建会话更换 UUID 即可。
- 已完成历史按 user／assistant 成对保存。失败、超时或完成前断开时，本轮问题和部分回答均不保存。
- 停止后客户端仍展示部分回答；这些文字不属于下一轮模型上下文。
- 正常完成的提交发生在发送 done 之前；若提交后断网导致 done 丢失，客户端可能认为失败，
  但服务端已经保存。这一版没有客户端完成确认或请求幂等协议，也不会自动重试。
- 同会话请求生成期间返回 409，不排队；不同会话可并发。
  点停止后立刻再发送，若服务器尚未处理完断开，可能暂时返回 409，可稍后手动再发。
- 默认保存最近 10 轮，输入历史加当前问题不超过 32,000 字符，按完整轮次从旧到新裁剪。
  这不是精确 token 预算；上下文过长时只保留最近连续的完整轮次。
- 流式回答正文上限 16,000 字符，超限发送 error 并放弃本轮。原模型输出 2048 token 限制保留。
- 最多 100 个会话，闲置一小时后过期，每 60 秒和新请求进入时清理；生成中的会话不清理。
  满容量时返回 503，不静默删除仍有效的历史。首轮失败会移除空会话。
- 配置集中在 `app/settings/session_settings.py`。存储方法同步执行且不含 await，
  仅在同一个异步事件循环调用，占用与提交不会在执行途中被另一个请求插入。
- 内存属于当前应用实例，只支持一个 Uvicorn worker；不要为此版本启用多 worker。
  服务重启、开发自动 reload 或会话过期后历史清空，相同 UUID 后续请求会成为新会话。
- session_id 只是会话标识，不是身份认证；当前用于本机学习，后续账号接入时需增加所有权校验。

## 手动验收建议

1. 在同一客户端会话说“我主要做 Android 开发”，等回答完成，再问“我刚才说我做什么开发”。
2. 新建会话后再问同一问题，确认不会得到上一段会话的已知信息。
3. 让模型生成较长回答并停止；随后重新发送，确认可以继续请求。
4. 两个请求使用相同 UUID，第一条仍生成时第二条应返回 409。
5. 用无效 UUID 或空白问题请求，应返回 422；原 POST /chat 仍只需 message。

本次未启动服务、调用模型、编译、运行测试或 lint；仅静态检查与查看 diff。
实际多轮效果、断开取消和并发行为仍需运行确认。新增直接依赖 anyio，更新环境可执行
`python -m pip install -e .`；当前 FastAPI 环境通常已间接安装它。
