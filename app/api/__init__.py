"""Compose feature routers without coupling them to each other."""

from fastapi import APIRouter

from app.api import auth, cases, catalog, emails, files, health, jobs, outlook, rules

router = APIRouter(prefix="/api")
for feature in (health, auth, catalog, cases, emails, files, jobs, outlook, rules):
    router.include_router(feature.router)
