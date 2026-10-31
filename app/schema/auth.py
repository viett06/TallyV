from pydantic import BaseModel, Field

from app.schema.common import View


class LoginRequest(BaseModel):
    username: str = Field(max_length=80)
    password: str = Field(max_length=200)


class UserView(View):
    username: str
    role: str
