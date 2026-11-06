"""DeepSeek 流式服务：逐段读取模型回答，不依赖 FastAPI。"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import aclosing

from openai import (
    APIConnectionError,
    APIError,
    APIResponseValidationError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AsyncStream,
)
from openai.types.chat import ChatCompletionChunk

from app.config import DeepSeekSettings
from app.services.deepseek import (
    DeepSeekConfigurationError,
    DeepSeekError,
    DeepSeekTimeoutError,
)


# 流式生成的总时限，独立于原非流式接口的 60 秒总时限。
STREAM_TOTAL_TIMEOUT_SECONDS = 180.0


async def stream_deepseek(
    message: str,
    settings: DeepSeekSettings,
) -> AsyncIterator[str]:
    """建立模型流并逐段返回文本，将 SDK 异常转换为服务层异常。"""
    if not settings.api_key:
        raise DeepSeekConfigurationError("服务端未配置 DEEPSEEK_API_KEY")

    try:
        async with asyncio.timeout(STREAM_TOTAL_TIMEOUT_SECONDS):
            async with AsyncOpenAI(
                api_key=settings.api_key,
                base_url=settings.base_url,
                # 网络各阶段超时沿用配置；读取时限制等待下一批数据的时间。
                timeout=settings.timeout_seconds,
                max_retries=0,
            ) as client:
                stream = await client.chat.completions.create(
                    model=settings.model,
                    messages=[{"role": "user", "content": message}],
                    stream=True,
                    max_tokens=settings.max_tokens,
                    extra_body={"thinking": {"type": "disabled"}},
                )

                # 正常结束、异常或取消时都关闭上游流，不继续消费模型输出。
                async with stream:
                    async with aclosing(read_model_stream(stream)) as parts:
                        async for text in parts:
                            yield text
    except (TimeoutError, APITimeoutError):
        raise DeepSeekTimeoutError("DeepSeek 流式响应超时，请稍后重试") from None
    except APIConnectionError:
        raise DeepSeekError("无法连接 DeepSeek，请检查服务端网络") from None
    except APIStatusError:
        raise DeepSeekError("DeepSeek 调用失败，请检查密钥、余额和服务状态") from None
    except (APIResponseValidationError, ValueError, AttributeError, TypeError):
        raise DeepSeekError("DeepSeek 返回的流式数据格式异常") from None
    except APIError:
        raise DeepSeekError("DeepSeek 流式调用失败，请稍后重试") from None


async def read_model_stream(
    stream: AsyncStream[ChatCompletionChunk],
) -> AsyncIterator[str]:
    """提取文本增量，只有收到正常结束标识且存在有效文本才视为完成。"""
    has_text = False

    async for chunk in stream:
        # 部分数据块只有用量等信息，没有回答选项。
        if not chunk.choices:
            continue

        choice = chunk.choices[0]
        text = choice.delta.content
        if text is not None:
            if not isinstance(text, str):
                raise DeepSeekError("DeepSeek 返回的流式文本格式异常")

            if text:
                has_text = has_text or bool(text.strip())
                yield text

        if choice.finish_reason == "stop":
            if not has_text:
                raise DeepSeekError("DeepSeek 未返回有效回答")
            return

        if choice.finish_reason == "length":
            raise DeepSeekError("回答达到输出长度上限，生成已中断")

        if choice.finish_reason is not None:
            raise DeepSeekError("模型未正常完成回答，生成已中断")

    # 网络 EOF 不等于回答完成，避免将中途断流误报为成功。
    raise DeepSeekError("模型连接提前结束，回答可能不完整，请重试")
