"""Compose feature routers without coupling them to each other."""

from fastapi import APIRouter

from app.api import auth, cases, catalog, emails, files, health, hr, jobs, outlook, rules
from app.assistant.api import router as assistant_router
from app.chatbot.api import legacy_router as chatbot_legacy_router
from app.chatbot.api import router as chatbot_router

router = APIRouter(prefix="/api")
for feature in (health, auth, catalog, cases, emails, files, jobs, outlook, rules, hr):
    router.include_router(feature.router)

router.include_router(assistant_router)
router.include_router(chatbot_router)
router.include_router(chatbot_legacy_router)
