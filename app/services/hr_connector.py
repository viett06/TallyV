"""Only HTTP transport knows the simulator URL/key; it never writes its tables."""

import hashlib
import hmac

import httpx
from pydantic import TypeAdapter, ValidationError

from app.core.config import settings
from app.core.errors import AppError
from app.core.i18n import message
from app.schema.hr import MockAttendanceView, MockReceiptView


def mock_api_key() -> str:
    configured = settings.hr_mock_api_key.get_secret_value()
    return configured or hmac.new(settings.secret_key.encode(), b"tallyv-hr-simulator-v1", hashlib.sha256).hexdigest()


class HrConnector:
    def health(self):
        return self._request("GET", "/api/health")

    def _request(self, method: str, path: str, payload: dict | None = None, *, allow_missing: bool = False):
        try:
            with httpx.Client(timeout=5, trust_env=False, follow_redirects=False) as client:
                response = client.request(
                    method,
                    settings.hr_mock_url + path,
                    json=payload,
                    headers={"Authorization": "Bearer " + mock_api_key()},
                )
            if response.status_code == 404 and allow_missing:
                return None
            if response.status_code in {404, 409, 422}:
                # Do not reflect arbitrary upstream text or credentials to HR.
                key = "hr.target_conflict" if response.status_code == 409 else "hr.target_record_missing"
                raise AppError(409, message(key))
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError):
            raise AppError(502, message("hr.unavailable")) from None

    def lookup(self, ids: list[str]) -> dict[str, dict]:
        if not ids:
            return {}
        data = self._request("POST", "/api/attendance/lookup", {"ids": sorted(set(ids))})
        try:
            records = TypeAdapter(list[MockAttendanceView]).validate_python(data)
        except ValidationError:
            raise AppError(502, message("hr.invalid_response")) from None
        result = {r.id: r.model_dump(mode="json") for r in records}
        if len(result) != len(records) or not result.keys() <= set(ids):
            raise AppError(502, message("hr.invalid_response"))
        return result

    def seed(self, records: list[dict]) -> dict:
        return self._request("POST", "/api/demo/seed", {"records": records})

    def receipt(self, request_id: str) -> dict | None:
        data = self._request("GET", f"/api/corrections/{request_id}", allow_missing=True)
        if data is None:
            return None
        try:
            return MockReceiptView.model_validate(data).model_dump(mode="json")
        except ValidationError:
            raise AppError(502, message("hr.invalid_response")) from None

    def apply(self, request_id: str, record_id: str, payload: dict) -> dict:
        data = self._request("PUT", f"/api/attendance/{record_id}/corrections/{request_id}", payload)
        try:
            receipt = MockReceiptView.model_validate(data)
        except ValidationError:
            raise AppError(502, message("hr.invalid_response")) from None
        if receipt.id != request_id or receipt.record_id != record_id:
            raise AppError(502, message("hr.invalid_response"))
        return receipt.model_dump(mode="json")


connector = HrConnector()
