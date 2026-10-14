import re

from pydantic import BaseModel, HttpUrl, field_validator


def validate_file_name(value: str) -> str:
    """校验文档 ID，避免路径字符和点号进入 Redis/Chroma 键名。"""
    value = value.strip()
    if not value:
        raise ValueError("file_name 不能为空")
    if re.search(r"[/\\.]", value):
        raise ValueError("file_name 不能包含路径分隔符或点号")
    if len(value) > 128:
        raise ValueError("file_name 过长，最多允许 128 个字符")
    return value


class IngestRequest(BaseModel):
    file_name: str
    s3_url: HttpUrl

    @field_validator("s3_url")
    @classmethod
    def must_be_pdf(cls, v: HttpUrl) -> HttpUrl:
        if not str(v).lower().endswith(".pdf"):
            raise ValueError(
                "URL 必须指向 PDF 文件，例如："
                "https://my-bucket.s3.amazonaws.com/policy.pdf"
            )
        return v

    @field_validator("file_name")
    @classmethod
    def safe_file_name(cls, v: str) -> str:
        return validate_file_name(v)


class IngestResult(BaseModel):
    doc_id: str
    status: str
    version: str | None = None
    added: int | None = None
    removed: int | None = None
    total: int | None = None
    reason: str | None = None


class IngestResponse(BaseModel):
    status: str
    data: IngestResult


class DocStatus(BaseModel):
    doc_id: str
    status: str
    file_name: str | None = None
    file_hash: str | None = None
    version: str | None = None
    total_chunks: str | None = None
    error: str | None = None
    updated_at: str | None = None


class DocListResponse(BaseModel):
    total: int
    docs: list[DocStatus]


class DeleteResponse(BaseModel):
    status: str
    doc_id: str
