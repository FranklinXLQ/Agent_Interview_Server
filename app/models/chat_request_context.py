"""一次生成请求使用的会话快照。"""

from dataclasses import dataclass

from app.models.conversation_turn import ConversationTurn


@dataclass(frozen=True)
class ChatRequestContext:
    """隔离本次问题、历史快照和请求标识，不提前修改已完成历史。"""

    session_id: str
    request_id: str
    message: str
    turns: tuple[ConversationTurn, ...]
