"""内存会话的数据定义。"""

from dataclasses import dataclass, field

from app.models.conversation_turn import ConversationTurn


@dataclass
class ChatSession:
    """保存已完成历史和当前请求占用状态。"""

    updated_at: float
    turns: list[ConversationTurn] = field(default_factory=list)
    # 每个请求有独立标识，旧请求的清理不能释放后续请求。
    active_request_id: str | None = None
