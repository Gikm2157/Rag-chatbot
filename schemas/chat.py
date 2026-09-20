from pydantic import BaseModel, field_validator


class ChatRequest(BaseModel):
    q: str

    @field_validator("q")
    @classmethod
    def question_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("问题不能为空")
        if len(v) > 2000:
            raise ValueError("问题过长，最多允许 2000 个字符")
        return v


class ChatResponse(BaseModel):
    status: str
    data: str
    sources: list[str]
