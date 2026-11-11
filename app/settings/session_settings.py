"""多轮对话的内存与上下文限制。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SessionSettings:
    """集中声明第一版会话策略，字符限制不等同于 token 精确计数。"""

    max_turns: int = 10
    # 模型输入正文总字符数，包括本次问题，按完整轮次裁剪。
    max_context_characters: int = 32_000
    # 同时限制流式回答累计大小，防止异常输出无界增长。
    max_answer_characters: int = 16_000
    max_sessions: int = 100
    idle_timeout_seconds: float = 3600.0
    cleanup_interval_seconds: float = 60.0
