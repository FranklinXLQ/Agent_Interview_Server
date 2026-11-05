"""集中管理模型配置和环境变量。"""

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class DeepSeekSettings:
    """
    DeepSeek 调用配置，创建后不再修改。
    """

    # 密钥不参与对象的文本展示，避免意外打印。
    api_key: str = field(repr=False)
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-flash"
    # 模型调用的总时限，包含连接、发送与读取响应。
    timeout_seconds: float = 60.0
    max_tokens: int = 2048


def get_deepseek_settings() -> DeepSeekSettings:
    """从当前服务进程的环境变量读取密钥，不在代码中保存密钥。"""
    return DeepSeekSettings(
        api_key=os.getenv("DEEPSEEK_API_KEY", "").strip(),
    )
