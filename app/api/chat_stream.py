"""流式问答路由：将模型文本转换为客户端可读取的 SSE 事件。"""

import json
import logging
from collections.abc import AsyncIterator
from contextlib import aclosing
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.config import DeepSeekSettings, get_deepseek_settings
from app.schemas.chat import ChatRequest
from app.services.deepseek import DeepSeekError
from app.services.deepseek_stream import stream_deepseek


router = APIRouter(tags=["问答"])
logger = logging.getLogger(__name__)


@router.post(
    "/chat/stream",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "SSE 事件流：delta 为文本增量，done 为完成，error 为生成失败。",
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        },
        503: {"description": "服务端缺少模型密钥，尚未开始流式响应。"},
    },
)
async def chat_stream(
    request: ChatRequest,
    settings: Annotated[DeepSeekSettings, Depends(get_deepseek_settings)],
) -> StreamingResponse:
    """校验必要配置后返回 SSE 响应，原有非流式接口保持独立。"""
    if not settings.api_key:
        raise HTTPException(status_code=503, detail="服务端未配置 DEEPSEEK_API_KEY")

    return StreamingResponse(
        send_chat_events(request.message, settings),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def send_chat_events(
    message: str,
    settings: DeepSeekSettings,
) -> AsyncIterator[str]:
    """转发文本并发送终止事件，生成失败后不再发送完成事件。"""
    try:
        # 下游取消读取时显式关闭生成器，使 SDK 流与客户端及时释放。
        async with aclosing(stream_deepseek(message, settings)) as parts:
            async for text in parts:
                yield format_event("delta", {"text": text})
    except DeepSeekError as error:
        yield format_event("error", {"message": str(error)})
    except Exception as error:
        # 不记录上游原始响应或异常详情，避免泄露密钥和问题内容。
        logger.error("流式问答发生未预期异常，类型：%s", type(error).__name__)
        yield format_event("error", {"message": "生成回答时发生异常，请稍后重试"})
    else:
        yield format_event("done", {})


def format_event(event: str, data: dict[str, str]) -> str:
    """使用 JSON 编码数据，以空行分隔事件，正确处理回答中的换行和引号。"""
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"
