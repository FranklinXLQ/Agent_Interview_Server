"""问答路由：接收请求、调用服务、转换为 HTTP 响应。"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.config import DeepSeekSettings, get_deepseek_settings
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.deepseek import (
    DeepSeekConfigurationError,
    DeepSeekError,
    DeepSeekTimeoutError,
    ask_deepseek,
)


router = APIRouter(tags=["问答"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    settings: Annotated[DeepSeekSettings, Depends(get_deepseek_settings)],
) -> ChatResponse:
    """
    返回模型的完整回答，并将服务层异常转换为 HTTP 错误。
    """
    try:
        answer = await ask_deepseek(request.message, settings)
    except DeepSeekConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from None
    except DeepSeekTimeoutError as error:
        raise HTTPException(status_code=504, detail=str(error)) from None
    except DeepSeekError as error:
        raise HTTPException(status_code=502, detail=str(error)) from None

    return ChatResponse(answer=answer)
