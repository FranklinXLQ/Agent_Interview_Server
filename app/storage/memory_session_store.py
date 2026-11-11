"""在单进程事件循环中管理会话，重启后清空历史。"""

from time import monotonic
from uuid import uuid4

from app.models.chat_session import ChatSession
from app.models.conversation_context import ConversationContext
from app.models.conversation_turn import ConversationTurn
from app.errors.session_error import SessionError
from app.settings.session_settings import SessionSettings


class MemorySessionStore:
    """提供历史快照、整轮提交、请求占用和过期清理。"""

    def __init__(self, settings: SessionSettings) -> None:
        """初始化存储；所有方法只在同一异步事件循环调用，不在线程池运行。"""
        self.settings = settings
        self._sessions: dict[str, ChatSession] = {}

    def begin_turn(self, session_id: str, message: str) -> ConversationContext:
        """原子地占用会话并返回裁剪后的历史，不把本次问题提前入库。"""
        self.cleanup_expired()
        session = self._sessions.get(session_id)
        if session is None:
            if len(self._sessions) >= self.settings.max_sessions:
                raise SessionError("capacity", "会话数量已达上限，请稍后重试")
            session = ChatSession(updated_at=monotonic())
            self._sessions[session_id] = session

        if session.active_request_id is not None:
            raise SessionError("busy", "当前会话正在生成回答，请先停止或等待完成")

        request_id = uuid4().hex
        session.active_request_id = request_id
        session.updated_at = monotonic()
        return ConversationContext(
            session_id=session_id,
            request_id=request_id,
            message=message,
            turns=self._select_turns(session.turns, len(message)),
        )

    def complete_turn(self, context: ConversationContext, answer: str) -> None:
        """生成正常完成后一次性提交问题和回答，并释放本次占用。"""
        session = self._sessions.get(context.session_id)
        if session is None or session.active_request_id != context.request_id:
            raise RuntimeError("会话请求已失效，不能保存回答")

        turn = ConversationTurn(user=context.message, assistant=answer)
        session.turns = list(self._select_turns(session.turns + [turn], 0))
        session.updated_at = monotonic()
        session.active_request_id = None

    def release_turn(self, context: ConversationContext) -> None:
        """失败或断开时只释放对应请求，重复清理不会影响后续请求。"""
        session = self._sessions.get(context.session_id)
        if session is None or session.active_request_id != context.request_id:
            return

        session.active_request_id = None
        session.updated_at = monotonic()
        # 没有成功历史的失败请求不保留空会话，及时归还容量。
        if not session.turns:
            del self._sessions[context.session_id]

    def cleanup_expired(self) -> None:
        """清理闲置过期会话，正在生成的会话不会被删除。"""
        now = monotonic()
        expired = [
            session_id
            for session_id, session in self._sessions.items()
            if session.active_request_id is None
            and now - session.updated_at >= self.settings.idle_timeout_seconds
        ]
        for session_id in expired:
            del self._sessions[session_id]

    def _select_turns(
        self,
        turns: list[ConversationTurn],
        current_characters: int,
    ) -> tuple[ConversationTurn, ...]:
        """从最近一轮开始选择连续完整问答，同时满足轮数与字符限制。"""
        selected: list[ConversationTurn] = []
        total = current_characters
        for turn in reversed(turns):
            if len(selected) >= self.settings.max_turns:
                break
            if total + turn.character_count > self.settings.max_context_characters:
                break
            selected.append(turn)
            total += turn.character_count

        return tuple(reversed(selected))
