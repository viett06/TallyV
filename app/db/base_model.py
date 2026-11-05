"""Single model registry for Alembic and isolated test database metadata."""

import app.assistant.models  # noqa: F401 -- registers Assistant tables
import app.models  # noqa: F401 -- import registers every table
from app.db.base import Base as Base
