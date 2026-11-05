"""问答接口的数据模型，用于请求校验和响应文档。"""

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    """客户端提交的问题。"""

    model_config = ConfigDict(str_strip_whitespace=True)

    message: str = Field(
        min_length=1,
        max_length=10000,
        description="用户的问题，首尾空白会自动去除",
    )


class ChatResponse(BaseModel):
    """服务端返回的完整回答。"""

    answer: str = Field(description="模型生成的完整回答")
