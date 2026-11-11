"""从当前应用获取对话服务，避免同步依赖进入线程池操作存储。"""

from fastapi import Request

from app.services.conversation import ConversationService


async def get_conversation_service(request: Request) -> ConversationService:
    """返回应用启动时创建的服务，同一应用的请求共享会话存储。"""
    return request.app.state.conversation_service
