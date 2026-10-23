from pydantic import BaseModel, Field, field_validator


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8, max_length=128)


class CreateEmployeeRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        value = value.strip()
        if not value or any(char.isspace() for char in value):
            raise ValueError("用户名不能为空或包含空白字符")
        return value


class UserResponse(BaseModel):
    id: str
    username: str
    role: str
    department_id: str | None = None


class LoginResponse(BaseModel):
    status: str
    user: UserResponse
