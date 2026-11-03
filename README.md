# Agent Interview Server

基于 Python + FastAPI 的 AI 应用服务端。目前仅包含可启动的应用骨架，尚未实现业务接口。

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

当前没有业务路由，访问根路径 `/` 返回 404 属于预期行为。
`--reload` 仅用于本地开发。

## 项目结构

```text
app/
├── __init__.py
└── main.py          # 应用创建与 ASGI 入口
pyproject.toml       # 项目元信息与依赖
README.md
```
