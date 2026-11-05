"""用于确认客户端和服务端连通的问候接口。"""

from fastapi import APIRouter


router = APIRouter(tags=["连通检查"])


@router.get("/hello")
def say_hello(name: str = "Franklin") -> dict[str, str]:
    """
    返回问候语，保留原有接口地址和响应格式。
    """
    return {"message": f"你好, {name}!"}
