import json
import os
from io import BytesIO
from pathlib import Path
from random import Random

import httpx
import pytest
from PIL import Image, ImageDraw
from pydantic import SecretStr
from sqlalchemy import select

from app import worker
from app.core.attendance import PUNCH_OUT
from app.core.config import settings
from app.models import AnalysisResult, AttendanceCase, EvidenceFile, EvidenceReference, EvidenceViewpoint, ProcessingJob
from app.services import evidence_facts, evidence_history
from app.services.storage import read_bytes


def _scene(seed: int, overlay: str = "", offset: int = 0) -> bytes:
    image = Image.new("RGB", (640, 420), "#ded8cd")
    draw = ImageDraw.Draw(image)
    rng = Random(seed)
    for _ in range(84):
        x, y = rng.randrange(48, 575) + offset, rng.randrange(43, 370) + offset
        width, height = rng.randrange(12, 34), rng.randrange(10, 30)
        ink = tuple(rng.randrange(25, 170) for _ in range(3))
        if rng.randrange(2):
            draw.rectangle((x, y, x + width, y + height), fill=ink)
        else:
            draw.polygon(((x, y), (x + width, y + 4), (x + 5, y + height)), fill=ink)
    if overlay:
        draw.rectangle((0, 0, 460, 35), fill="black")
        draw.text((12, 8), overlay, fill="white")
    output = BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


def _add_case(db, client, day, content, employee="MP001"):
    response = client.post(
        "/api/cases",
        data={
            "employee_id": employee,
            "work_date": day,
            "shift": "22:00-06:00",
            "punch": "OUT",
            "explanation": "Máy mất kết nối khi chấm ra.",
        },
        files=[("evidence", ("test.png", content, "image/png"))],
    )
    assert response.status_code == 201, response.text
    case = db.get(AttendanceCase, response.json()["id"])
    return case, db.scalar(select(EvidenceFile).where(EvidenceFile.version_id == case.active_version_id))


def _index_sample(db, case, evidence):
    case.hr_status = "CONFIRMED"
    return evidence_history.index_reference(db, evidence, read_bytes(evidence.path))


@pytest.fixture
def checkpoint(monkeypatch):
    value = os.getenv("TALLYV_TEST_IMAGE_MODEL")
    if not value or not Path(value).is_file():
        pytest.skip("Set TALLYV_TEST_IMAGE_MODEL to the MobileNetV2 checkpoint")
    pytest.importorskip("cv2")
    monkeypatch.setattr(settings, "evidence_history_model_path", Path(value))
    monkeypatch.setattr(settings, "evidence_history_enabled", True)
    return Path(value)


def test_ambiguous_event_clock_and_overnight_comparison():
    data = {"employee_id": "MP001", "date": "2026-10-01", "shift": "22:00–06:00", "punch": PUNCH_OUT}
    evidence = {"date": "2026-10-02", "employee_id": "mp001"}
    evidence_facts.add_ocr_facts(evidence, "01:10\n14:15", "01:10\n14:15")
    assert evidence["time_source"] == "AMBIGUOUS"
    assert evidence_facts.compare(evidence, data)["work_date_match"] == "UNKNOWN"
    evidence_facts.add_ocr_facts(evidence, "01:10\nGio quet: 05:58", "01:10\ngio quet: 05:58")
    assert evidence["time_source"] == "LABELED_EVENT"
    result = evidence_facts.compare(evidence, data)
    assert (result["employee_match"], result["work_date_match"], result["shift_match"]) == ("MATCH",) * 3
    assert result["minutes_from_expected_punch"] == -2
    evidence.pop("date")
    assert evidence_facts.compare(evidence, data)["shift_match"] == "UNKNOWN"


def test_retrieval_across_periods_and_reuse(checkpoint, context):
    sessions, client = context
    first = _scene(11)
    with sessions() as db:
        sample_case, sample = _add_case(db, client, "2026-09-01", first)
        result = _index_sample(db, sample_case, sample)
        assert result["status"] == "NO_REFERENCE"
        group = db.get(EvidenceViewpoint, result["viewpoint_id"])
        group.location = "Khu A mô phỏng"
        group.location_basis = "Biển khu A trong ảnh mẫu mô phỏng"
        group.location_evidence_id = sample.id

        newer_case, newer = _add_case(db, client, "2026-10-01", _scene(22), employee="MP002")
        assert _index_sample(db, newer_case, newer)["status"] in {"NO_REFERENCE", "NO_MATCH"}

        _, query = _add_case(db, client, "2026-11-01", _scene(11, "05:58 02/11/2026", offset=9), employee="MP002")
        result = evidence_history.compare(db, query, read_bytes(query.path))
        assert result["status"] == "KNOWN_VIEW"
        assert result["location"] == "Khu A mô phỏng"
        assert result["matches"][0]["reference_evidence_id"] == sample.id

        _, reused = _add_case(db, client, "2026-11-02", first)
        assert evidence_history.compare(db, reused, read_bytes(reused.path))["duplicate_kind"] == "EXACT"
        assert db.get(EvidenceReference, reused.id) is None

        lossy = BytesIO()
        with Image.open(BytesIO(first)) as image:
            image.save(lossy, "JPEG", quality=80)
        _, near = _add_case(db, client, "2026-11-03", lossy.getvalue())
        assert evidence_history.compare(db, near, read_bytes(near.path))["duplicate_kind"] == "NEAR"

        sample_ref = db.get(EvidenceReference, sample.id)
        sample_ref.excluded = True
        assert evidence_history.compare(db, query, read_bytes(query.path))["status"] != "KNOWN_VIEW"


def test_face_background_mask_and_missing_detail(checkpoint, monkeypatch):
    import numpy as np

    from app.services import evidence_image_features as features

    class Detector:
        def detectMultiScale(self, *_args, **_kwargs):
            return np.array([[228, 103, 175, 160]])

    monkeypatch.setattr(features, "_face_detector", lambda _: Detector())
    scene = features.open_image(_scene(11))
    background = features.background(scene, {"scene": {"kind": "FACE"}, "kind": "ATTENDANCE"})
    assert background is not None
    assert list(background[0][160, 300]) == [124, 116, 104]
    assert features.background(Image.new("RGB", (640, 420), "white"), {"scene": {"kind": "FACE"}}) is None


@pytest.mark.parametrize(
    ("overstates", "model_shift", "status"),
    [(0.02, "MATCH", "PASSED"), (0.92, "MATCH", "NEEDS_REVIEW"), (0.02, "MISMATCH", "NEEDS_REVIEW")],
)
def test_history_flows_through_gemini_jev_and_case_detail(
    checkpoint, context, monkeypatch, overstates, model_shift, status
):
    sessions, client = context
    monkeypatch.setattr(settings, "processing_mode", "GEMINI")
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr("synthetic"))
    monkeypatch.setattr(settings, "jev_enabled", True)
    monkeypatch.setattr(settings, "jev_api_key", SecretStr("synthetic"))
    monkeypatch.setattr(settings, "ocr_enabled", True)
    monkeypatch.setattr(
        "app.services.analysis.read_text",
        lambda *args, **kwargs: "02/10/2026\nGiờ quét: 05:58\nMã máy: PRIVATE-17\nMất kết nối",
    )

    with sessions() as db:
        sample_case, sample = _add_case(db, client, "2026-09-01", _scene(11))
        assert _index_sample(db, sample_case, sample)["status"] == "NO_REFERENCE"
        db.commit()
        case, _ = _add_case(db, client, "2026-10-01", _scene(11, "05:58", offset=9))
        case_id = case.id

    assert client.post(f"/api/cases/{case_id}/reanalyze").status_code == 200
    calls = []

    def respond(request):
        body = json.loads(request.content)
        calls.append(body)
        if request.url.host == "api.typesafe.ai":
            return httpx.Response(
                200,
                json={
                    "answers": {
                        "label_supported": {"type": "noul", "noul": 0.92},
                        "explanation_overstates": {"type": "noul", "noul": overstates},
                    }
                },
            )
        proposal = {
            "category": "DEVICE_ERROR",
            "reason": "Ảnh hiển thị máy mất kết nối." if status == "PASSED" else "Ảnh được chụp tại bệnh viện.",
            "supporting_evidence_refs": [1],
            "evidence_matches": [
                {
                    "evidence_ref": 1,
                    "employee_match": "UNKNOWN",
                    "work_date_match": "MATCH",
                    "shift_match": model_shift,
                },
            ],
        }
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(proposal)}]}},
                ]
            },
        )

    http_client = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: http_client(transport=httpx.MockTransport(respond), **kwargs))
    for _ in range(12):
        if not worker.run_one(sessions):
            break
    gemini_case = json.loads(calls[-2]["contents"][0]["parts"][0]["text"])["case"]
    assert calls[-1]["state"]["case"] == gemini_case
    assert calls[-1]["state"]["proposal"]["supporting_evidence_refs"] == [1]
    image = gemini_case["evidence"][0]
    assert image["image_history"]["status"] == "KNOWN_VIEW_UNLOCATED"
    assert image["attendance_comparison"]["shift_match"] == "MATCH"
    assert image["observed_states"] == ["DEVICE_ERROR"]
    assert "PRIVATE-17" not in json.dumps(calls)
    assert "05:58" not in json.dumps(calls)
    detail = client.get(f"/api/cases/{case_id}").json()
    assert detail["analysis"]["extracted"]["jev_verification"]["status"] == status
    assert detail["hr_status"] == "PENDING_REVIEW"


def test_partial_matches_create_provisional_viewpoint(checkpoint, context):
    from app.services import evidence_image_features as features

    sessions, client = context
    first_image = _scene(11)
    second_image = _scene(22)
    composite = features.open_image(first_image)
    composite.paste(features.open_image(second_image).crop((0, 210, 640, 420)), (0, 210))
    output = BytesIO()
    composite.save(output, "PNG")

    with sessions() as db:
        first_case, first = _add_case(db, client, "2026-09-01", first_image)
        second_case, second = _add_case(db, client, "2026-10-01", second_image, employee="MP002")
        first_result = _index_sample(db, first_case, first)
        second_result = _index_sample(db, second_case, second)
        query_case, query = _add_case(db, client, "2026-11-01", output.getvalue())
        result = evidence_history.compare(db, query, read_bytes(query.path))
        assert result["status"] == "AMBIGUOUS", result
        assert {match["reference_evidence_id"] for match in result["matches"]} == {first.id, second.id}
        assert db.get(EvidenceReference, query.id) is None
        result = _index_sample(db, query_case, query)
        assert result["viewpoint_id"] not in {first_result["viewpoint_id"], second_result["viewpoint_id"]}
        assert db.get(EvidenceViewpoint, result["viewpoint_id"]).location is None
        assert _index_sample(db, query_case, query)["viewpoint_id"] == result["viewpoint_id"]


def test_missing_checkpoint_keeps_ocr_and_attendance(checkpoint, context, monkeypatch):
    from app.services.analysis import read_evidence

    sessions, client = context
    monkeypatch.setattr(settings, "evidence_history_model_path", None)
    monkeypatch.setattr(settings, "ocr_enabled", True)
    monkeypatch.setattr("app.services.analysis.read_text", lambda *a, **kw: "02/10/2026 05:58 Camera: CC-7")
    with sessions() as db:
        case, evidence = _add_case(db, client, "2026-10-01", _scene(11))
        data = {"employee_id": case.employee_id, "date": "2026-10-01", "shift": "22:00-06:00", "punch": PUNCH_OUT}
        read_evidence(evidence, data, db)
        assert evidence.extracted["image_history"]["status"] == "UNAVAILABLE"
        assert evidence.extracted["attendance_comparison"]["shift_match"] == "MATCH"
        assert evidence.extracted["camera_id"] == "CC-7"


@pytest.mark.parametrize("bulk", [False, True])
def test_worker_indexes_only_after_hr_confirmation(checkpoint, context, monkeypatch, bulk):
    from app.services import evidence_image_features as features

    sessions, client = context
    with sessions() as db:
        case, evidence = _add_case(db, client, "2026-10-01", _scene(11))
        case_id, version_id, evidence_id = case.id, case.active_version_id, evidence.id
        content = read_bytes(evidence.path)
        assert evidence_history.compare(db, evidence, content)["status"] == "NO_REFERENCE"
        assert evidence_history.index_reference(db, evidence, content)["status"] == "OUT_OF_SCOPE"
        assert db.get(EvidenceReference, evidence_id) is None
        assert db.scalar(select(ProcessingJob).where(ProcessingJob.kind == "INDEX_EVIDENCE")) is None
        analysis = db.scalar(select(AnalysisResult).where(AnalysisResult.version_id == version_id))
        analysis.status, analysis.assessment, analysis.category = "COMPLETED", "SUFFICIENT", "DEVICE_ERROR"
        db.commit()

    def confirm():
        if bulk:
            return client.post("/api/cases/bulk-confirm", json={"ids": [case_id], "acknowledged": True})
        return client.patch(f"/api/cases/{case_id}/review", json={"status": "CONFIRMED", "category": "DEVICE_ERROR"})

    assert confirm().status_code == 200
    with sessions() as db:
        assert db.get(AttendanceCase, case_id).hr_status == "CONFIRMED"
        assert db.get(EvidenceReference, evidence_id) is None
        assert db.scalar(select(ProcessingJob).where(ProcessingJob.kind == "INDEX_EVIDENCE")).status == "PENDING"

    assert worker.run_one(sessions)
    with sessions() as db:
        indexed = db.get(EvidenceReference, evidence_id)
        assert len(indexed.embedding) == 1280
        assert indexed.viewpoint_id
        assert db.scalar(select(ProcessingJob).where(ProcessingJob.kind == "INDEX_EVIDENCE")).status == "DONE"

    if not bulk:
        embeddings = []
        embed = features.embedding

        def count_embedding(background):
            embeddings.append(True)
            return embed(background)

        monkeypatch.setattr(features, "embedding", count_embedding)
        assert confirm().status_code == 200
        assert worker.run_one(sessions)
        assert embeddings == [True]
        with sessions() as db:
            assert len(list(db.scalars(select(EvidenceReference)))) == 1


def test_reopened_case_is_not_indexed_or_used_as_reference(checkpoint, context):
    sessions, client = context
    with sessions() as db:
        case, evidence = _add_case(db, client, "2026-10-01", _scene(11))
        case_id, version_id, evidence_id = case.id, case.active_version_id, evidence.id
        _index_sample(db, case, evidence)
        evidence_history.enqueue_confirmed(db, version_id)
        db.commit()

    reopened = client.patch(
        f"/api/cases/{case_id}/review",
        json={"status": "NEEDS_INFO", "category": "DEVICE_ERROR", "note": "Cần thêm ảnh."},
    )
    assert reopened.status_code == 200
    assert worker.run_one(sessions)
    with sessions() as db:
        assert evidence_history.active_evidence(db, evidence_id, confirmed_only=True) is None
        _, query = _add_case(db, client, "2026-11-01", _scene(11, "05:58", offset=9))
        assert evidence_history.compare(db, query, read_bytes(query.path))["status"] == "NO_REFERENCE"
