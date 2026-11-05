from typing import Literal

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class UserView(BaseModel):
    id: int
    username: str
    role: str


class MessageRequest(BaseModel):
    text: str = Field(min_length=1, max_length=6000)
    attachment_ids: list[str] = Field(default_factory=list, max_length=6)
    request_key: str = Field(min_length=8, max_length=80)
    task_mode: Literal["auto", "documents", "data"] = "auto"


class ParagraphEdit(BaseModel):
    id: str
    text: str = Field(max_length=12000)


class ArtifactEdit(BaseModel):
    revision: int = Field(ge=1)
    paragraphs: list[ParagraphEdit] = Field(max_length=500)


class ReviewRequest(BaseModel):
    revision: int = Field(ge=1)
    reviewed: bool


class RoleRequest(BaseModel):
    role: Literal["template", "data"]


class AttachmentView(BaseModel):
    id: str
    name: str
    role: str
    size: int
    sha256: str


class MessageView(BaseModel):
    id: str
    role: str
    content: str
    details: dict
    created_at: str


class ArtifactView(BaseModel):
    id: str
    run_id: str
    name: str
    label: str
    paragraphs: list[dict]
    provenance: dict
    email: dict
    revision: int
    reviewed: bool


class RunView(BaseModel):
    id: str
    status: str
    method: str
    summary: str
    plan: dict
    report: list[dict]
    artifacts: list[ArtifactView]
    job: dict | None
    kind: str = "DOCUMENT"
    revision: int = 1
    parent_run_id: str | None = None
    steps: list[dict] = Field(default_factory=list)
    task: dict = Field(default_factory=dict)


class ConversationView(BaseModel):
    id: str
    title: str
    updated_at: str


class ConversationDetail(ConversationView):
    messages: list[MessageView]
    attachments: list[AttachmentView]
    runs: list[RunView]


class MessageAck(BaseModel):
    conversation_id: str
    message_id: str
    run_id: str | None
