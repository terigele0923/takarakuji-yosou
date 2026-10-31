from pydantic import BaseModel, Field, field_validator


class AgentRequest(BaseModel):
    # 質問は 1000 文字まで
    message: str = Field(max_length=1000)
    # 会話を見分ける番号（同じ番号なら前のやり取りを覚えている）
    thread_id: str = Field(min_length=1, max_length=64)

    # 空白だけの質問はエラーにする
    @field_validator("message")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("質問を入力してください")
        return value


class AgentResponse(BaseModel):
    answer: str
