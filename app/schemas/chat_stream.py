"""流式对话请求：独立增加会话标识，不改变普通问答接口。"""

from uuid import UUID

from pydantic import Field

from app.schemas.chat import ChatRequest


class ChatStreamRequest(ChatRequest):
    """客户端每轮提交当前问题和同一个会话标识。"""

    session_id: UUID = Field(description="客户端生成的会话 UUID，新建会话时更换")
