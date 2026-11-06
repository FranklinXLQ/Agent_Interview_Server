"""应用入口：创建 FastAPI 应用并注册路由。"""

from fastapi import FastAPI

from app.api import chat, chat_stream, hello


def create_app() -> FastAPI:
    """创建应用，并集中注册各业务模块的路由。"""
    app = FastAPI(
        title="Agent Interview Server",
        version="0.1.0",
        description="AI 应用服务端",
    )
    app.include_router(hello.router)
    app.include_router(chat.router)
    app.include_router(chat_stream.router)
    return app


# Uvicorn 通过 app.main:app 加载这个应用实例。
app = create_app()
