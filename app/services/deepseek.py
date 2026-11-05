"""DeepSeek 服务：只负责模型调用，不依赖 FastAPI。"""

import asyncio

import httpx

from app.config import DeepSeekSettings


class DeepSeekError(Exception):
    """模型调用失败，异常信息可安全展示给客户端。"""


class DeepSeekConfigurationError(DeepSeekError):
    """服务端缺少必要配置。"""


class DeepSeekTimeoutError(DeepSeekError):
    """等待模型响应超时。"""


async def ask_deepseek(message: str, settings: DeepSeekSettings) -> str:
    """向 DeepSeek 发送单次问题，并返回完整回答。"""
    if not settings.api_key:
        raise DeepSeekConfigurationError("服务端未配置 DEEPSEEK_API_KEY")

    try:
        # 限制整次模型调用耗时，避免各网络阶段分别计时后超过客户端等待时间。
        async with asyncio.timeout(settings.timeout_seconds):
            async with httpx.AsyncClient(timeout=settings.timeout_seconds) as client:
                response = await client.post(
                    f"{settings.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {settings.api_key}"},
                    json={
                        "model": settings.model,
                        "messages": [{"role": "user", "content": message}],
                        # 显式使用非思考模式，保持当前单次问答的行为。
                        "thinking": {"type": "disabled"},
                        "stream": False,
                        "max_tokens": settings.max_tokens,
                    },
                )
                response.raise_for_status()
    except (TimeoutError, httpx.TimeoutException):
        raise DeepSeekTimeoutError("DeepSeek 响应超时，请稍后重试") from None
    except httpx.HTTPStatusError:
        raise DeepSeekError("DeepSeek 调用失败，请检查密钥、余额和服务状态") from None
    except httpx.RequestError:
        raise DeepSeekError("无法连接 DeepSeek，请检查服务端网络") from None

    return parse_answer(response)


def parse_answer(response: httpx.Response) -> str:
    """提取并检查模型回答，不向客户端透传上游原始数据。"""
    try:
        answer = response.json()["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise DeepSeekError("DeepSeek 返回的数据格式异常") from None

    if not isinstance(answer, str) or not answer.strip():
        raise DeepSeekError("DeepSeek 未返回有效回答")

    return answer
