from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.config import ROOT

MAX_PDF_BYTES = 20 * 1024 * 1024
DOCUMENT_UPLOAD_PATHS = frozenset({"/api/chatbot/documents", "/api/policy-documents"})


class ChatbotSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore", hide_input_in_errors=True)

    policy_rerank_model: str = "cohere/rerank-4-fast"
    policy_answer_model: str = "google/gemini-2.5-flash"
    policy_ocr_model: str = "google/gemini-2.5-flash"


settings = ChatbotSettings()
