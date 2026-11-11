"""一轮完整问答的数据定义。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ConversationTurn:
    """成对保存成功的问题与回答，避免留下不完整的上下文。"""

    user: str
    assistant: str

    @property
    def character_count(self) -> int:
        """计算本轮正文字符数，作为第一版历史大小限制。"""
        return len(self.user) + len(self.assistant)
