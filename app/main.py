"""服务端应用入口。"""

from fastapi import FastAPI


def create_app() -> FastAPI:
    """创建服务端应用，后续在此注册业务路由。"""
    return FastAPI(
        title="Agent Interview Server",
        version="0.1.0",
        description="AI 应用服务端",
    )


# ASGI 应用实例，供 Uvicorn 启动服务。
app = create_app()
