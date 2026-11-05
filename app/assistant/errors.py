from app.core.errors import AppError as AppError


class InputError(AppError):
    def __init__(self, detail: str, *, issues=None):
        self.issues = issues or []
        super().__init__(422, detail)
