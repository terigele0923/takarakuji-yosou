from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    # 質問は 1000 文字まで
    question: str = Field(max_length=1000)

    # 空白だけの質問はエラーにする
    @field_validator("question")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("質問を入力してください")
        return value


class ChatResponse(BaseModel):
    answer: str
