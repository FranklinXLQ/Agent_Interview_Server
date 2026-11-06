"""DeepSeek 服务：通过 OpenAI SDK 调用模型，不依赖 FastAPI。"""

import asyncio

from openai import (
    APIConnectionError,
    APIError,
    APIResponseValidationError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
)
from openai.types.chat import ChatCompletion

from app.config import DeepSeekSettings


class DeepSeekError(Exception):
    """模型调用失败，异常信息可安全展示给客户端。"""


class DeepSeekConfigurationError(DeepSeekError):
    """服务端缺少必要配置。"""


class DeepSeekTimeoutError(DeepSeekError):
    """等待模型响应超时。"""


async def ask_deepseek(message: str, settings: DeepSeekSettings) -> str:
    """通过异步 SDK 向 DeepSeek 发送单次问题，并返回完整回答。"""
    if not settings.api_key:
        raise DeepSeekConfigurationError("服务端未配置 DEEPSEEK_API_KEY")

    try:
        # 限制整次模型调用耗时，客户端仍保留额外等待时间以接收超时错误。
        async with asyncio.timeout(settings.timeout_seconds):
            async with AsyncOpenAI(
                api_key=settings.api_key,
                base_url=settings.base_url,
                timeout=settings.timeout_seconds,
                # 关闭 SDK 自动重试，保持一次请求只尝试调用一次模型。
                max_retries=0,
            ) as client:
                response = await client.chat.completions.create(
                    model=settings.model,
                    messages=[{"role": "user", "content": message}],
                    stream=False,
                    max_tokens=settings.max_tokens,
                    # 厂商扩展参数通过 extra_body 传递，显式关闭思考模式。
                    extra_body={"thinking": {"type": "disabled"}},
                )
    except (TimeoutError, APITimeoutError):
        raise DeepSeekTimeoutError("DeepSeek 响应超时，请稍后重试") from None
    except APIConnectionError:
        raise DeepSeekError("无法连接 DeepSeek，请检查服务端网络") from None
    except APIStatusError:
        raise DeepSeekError("DeepSeek 调用失败，请检查密钥、余额和服务状态") from None
    except (APIResponseValidationError, ValueError):
        raise DeepSeekError("DeepSeek 返回的数据格式异常") from None
    except APIError:
        raise DeepSeekError("DeepSeek 调用失败，请稍后重试") from None

    return parse_answer(response)


def parse_answer(response: ChatCompletion) -> str:
    """从 SDK 响应对象提取并检查模型回答，不透传上游原始数据。"""
    try:
        answer = response.choices[0].message.content
    except (AttributeError, IndexError, TypeError):
        raise DeepSeekError("DeepSeek 返回的数据格式异常") from None

    if not isinstance(answer, str) or not answer.strip():
        raise DeepSeekError("DeepSeek 未返回有效回答")

    return answer
