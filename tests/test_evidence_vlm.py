"""Privacy-first evidence pipeline: pixels, async stage ordering and fail-closed egress."""

import asyncio
from base64 import b64decode
from io import BytesIO
from json import loads

import httpx
import numpy as np
import pytest
from PIL import Image, ImageDraw, PngImagePlugin
from pydantic import SecretStr, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from tallyv_image_preprocessing import ProfileSet, process
from tallyv_image_preprocessing.processor import decode

from app import worker
from app.core.config import settings
from app.demo.generate import workbook
from app.models import AnalysisResult, AttendanceCase, EvidenceFile, EvidencePrivacy, ProcessingJob
from app.schema.evidence_privacy import AssessmentRequest
from app.services import analysis, image_background
from app.services.evidence_privacy import plan_batch
from app.services.imports import synchronize
from scripts.configure_evidence_privacy import build_profile
from tests.helpers import Provider, ingest, row


def sample(kind="FACEID"):
    image = Image.new("RGB", (160, 120), (90, 90, 90))
    draw = ImageDraw.Draw(image)
    color = (20, 180, 240) if kind == "FACEID" else (240, 140, 20)
    for x in [0, 144]:
        draw.rectangle((x, 0, x + 15, 11), fill=color)
        draw.line((x, 0, x + 15, 11), fill="white", width=2)
    draw.rectangle((35, 25, 79, 84), fill=(210, 160, 130))
    draw.rectangle((110, 30, 149, 79), fill=(230, 230, 230))
    draw.text((112, 42), "ERROR", fill="black")
    draw.text((10, 103), "PII: MP001", fill="white")
    info = PngImagePlugin.PngInfo()
    info.add_text("employee", "Private name")
    output = BytesIO()
    image.save(output, format="PNG", pnginfo=info)
    return output.getvalue()


def profile(kind="FACEID"):
    return build_profile(
        sample(kind),
        {
            "id": kind.lower(),
            "kind": kind,
            "enabled": True,
            "anchors": [{"rect": {"x": x, "y": 0, "w": 16, "h": 12}} for x in [0, 144]],
            "keep_regions": [{"x": 0, "y": 0, "w": 160, "h": 120}],
            "pii_regions": [{"x": 0, "y": 100, "w": 160, "h": 20}, {"x": 35, "y": 25, "w": 45, "h": 60}],
            "face_region": {"x": 25, "y": 15, "w": 65, "h": 80} if kind == "FACEID" else None,
        },
    )


def test_fixed_layout_covers_face_and_identifiers_without_any_model(monkeypatch):
    monkeypatch.setattr(httpx, "Client", lambda **kw: pytest.fail("Preprocessing must not use HTTP"))
    config = ProfileSet(profiles=[profile(), profile("DEVICE_ERROR")])
    original = sample()
    outcome = process(original, config)
    assert outcome.status == "READY" and outcome.image.kind == "FACEID"
    pixels = decode(outcome.image.content)
    assert (pixels[15:95, 25:90] == 0).all()
    assert (pixels[100:, :] == 0).all()
    assert np.array_equal(pixels[30:80, 110:150], decode(original)[30:80, 110:150])
    assert Image.open(BytesIO(outcome.image.content)).info == {}
    assert Image.open(BytesIO(original)).info["employee"] == "Private name"


@pytest.mark.parametrize("kind", ["FACEID", "DEVICE_ERROR"])
def test_only_known_layouts_are_released(kind):
    outcome = process(sample(kind), ProfileSet(profiles=[profile(), profile("DEVICE_ERROR")]))
    assert outcome.status == "READY" and outcome.image.kind == kind


@pytest.mark.parametrize("case", ["unknown", "ambiguous", "disabled", "corrupt", "blank", "resized"])
def test_unsupported_inputs_are_manual_only(case):
    config = ProfileSet(profiles=[profile()])
    content = sample()
    if case == "unknown":
        content = sample("DEVICE_ERROR")
    elif case == "ambiguous":
        config.profiles.append(profile().model_copy(update={"id": "another"}))
    elif case == "disabled":
        config.profiles[0].enabled = False
    elif case == "corrupt":
        content = b"not an image"
    elif case in {"blank", "resized"}:
        image = Image.new("RGB", (160, 120)) if case == "blank" else Image.open(BytesIO(content)).resize((80, 60))
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        content = buffer.getvalue()
    result = process(content, config)
    assert result.status == "MANUAL_REVIEW" and result.image is None


def test_non_allowlisted_pixels_are_always_black():
    p = profile()
    p.keep_regions = [p.keep_regions[0].model_copy(update={"x": 110, "y": 30, "w": 40, "h": 50})]
    result = process(sample(), ProfileSet(profiles=[p]))
    pixels = decode(result.image.content)
    assert not pixels[:30].any() and not pixels[80:].any() and not pixels[:, :110].any()


class BackgroundCapture:
    def __init__(self, run):
        self.run = run
        self.batches = []

    async def collect(self, batch, sessions):
        self.batches.append((batch, sessions))

    def finish(self):
        batches, self.batches = self.batches, []
        for batch, sessions in batches:
            asyncio.run(self.run(batch, sessions))


@pytest.fixture
def pipeline(context, monkeypatch, tmp_path):
    sessions, client = context
    path = tmp_path / "profiles.json"
    path.write_text(ProfileSet(profiles=[profile(), profile("DEVICE_ERROR")]).model_dump_json())
    monkeypatch.setattr(settings, "evidence_privacy_profiles_path", path)
    monkeypatch.setattr(settings, "evidence_vision_provider", "openrouter")
    monkeypatch.setattr(settings, "openrouter_api_key", SecretStr("synthetic"))
    background = BackgroundCapture(image_background.run_batch)
    monkeypatch.setattr(image_background, "run_batch", background.collect)
    return sessions, client, path, background


def add_case(sessions, images):
    with sessions() as db:
        ingest(db, workbook([row(explanation="Máy lỗi thiết bị.")], {2: images}))
        return db.scalar(select(AttendanceCase.id))


def inference(monkeypatch, *, relation="SUPPORTS", refs=(1,), category="DEVICE_ERROR"):
    requests = []

    def handler(request):
        requests.append(request)
        import json

        output = {
            "category": category,
            "reason": "Đối chiếu ảnh đã che.",
            "evidence_assessments": [
                {
                    "evidence_ref": ref,
                    "relation": relation,
                    "observation": "Thiết bị hiển thị lỗi.",
                    "limitations": "Không xác minh danh tính.",
                }
                for ref in refs
            ],
        }
        return httpx.Response(
            200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(output)}}]}
        )

    real_client = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    return requests


def test_api_defers_direct_background_call_without_image_queue(pipeline, monkeypatch):
    sessions, client, _, background = pipeline
    case_id = add_case(sessions, [sample()])
    requests = inference(monkeypatch)
    assert client.post("/api/analysis").json() == {"queued": 1}
    assert len(background.batches) == 1 and requests == []
    with sessions() as db:
        assert db.scalar(select(AnalysisResult)).status == "WAITING_PRIVACY"
        assert not list(
            db.scalars(
                select(ProcessingJob).where(ProcessingJob.kind.in_(["PREPROCESS_EVIDENCE", "RELEASE_VLM", "ANALYZE"]))
            )
        )
    background.finish()
    assert len(requests) == 1
    parts = loads(requests[0].content)["messages"][0]["content"]
    sent = b64decode(parts[0]["image_url"]["url"].split(",", 1)[1])
    assert not decode(sent)[15:95, 25:90].any() and not decode(sent)[100:].any()
    assert "MP001" not in parts[1]["text"]
    detail = client.get(f"/api/cases/{case_id}").json()
    assert detail["analysis"]["status"] == "COMPLETED" and detail["analysis"]["assessment"] == "SUFFICIENT"
    e = detail["versions"][0]["evidence"][0]
    assert e["privacy"]["vlm_allowed"]
    assert client.get(e["privacy"]["preview_url"]).content == sent
    with sessions() as db:
        first_path = db.scalar(select(EvidencePrivacy)).sanitized_path
        assert first_path != db.scalar(select(EvidenceFile)).path
    client.post("/api/privacy/preprocess")
    background.finish()
    with sessions() as db:
        assert db.scalar(select(EvidencePrivacy)).sanitized_path == first_path
    assert len(requests) == 1  # Preprocessing-only never triggers another inference.


def test_unknown_images_have_no_vlm_release_or_override(pipeline, monkeypatch):
    sessions, client, _, background = pipeline
    buffer = BytesIO()
    Image.new("RGB", (180, 120), "gray").save(buffer, format="PNG")
    case_id = add_case(sessions, [buffer.getvalue()])
    with sessions() as db:
        result = db.scalar(select(AnalysisResult))
        result.evidence_checks = [{"legacy_text": "historical identifying observations"}]
        db.commit()
    requests = inference(monkeypatch)
    client.post("/api/analysis")
    background.finish()
    assert requests == []
    detail = client.get(f"/api/cases/{case_id}").json()
    assert detail["analysis"]["status"] == "MANUAL_REVIEW" and not detail["bulk_eligible"]
    assert "legacy_text" not in str(detail["analysis"]["evidence_checks"])
    e = detail["versions"][0]["evidence"][0]
    assert not e["privacy"]["vlm_allowed"] and not e["privacy"]["preview_url"]
    assert client.get(f"/api/evidence/{e['id']}/sanitized").status_code == 409
    assert client.post(f"/api/evidence/{e['id']}/approve-vlm").status_code in {404, 405}
    client.post(f"/api/cases/{case_id}/reanalyze")
    background.finish()
    assert requests == []


def test_mixed_case_sends_only_sanitized_subset_and_requires_manual_review(pipeline, monkeypatch):
    sessions, client, _, background = pipeline
    buffer = BytesIO()
    Image.new("RGB", (90, 90), "white").save(buffer, format="PNG")
    case_id = add_case(sessions, [sample(), buffer.getvalue(), sample("DEVICE_ERROR")])
    requests = inference(monkeypatch, refs=(1, 2))
    client.post("/api/analysis")
    background.finish()
    assert len(requests) == 1
    parts = loads(requests[0].content)["messages"][0]["content"]
    assert sum(p["type"] == "image_url" for p in parts) == 2
    detail = client.get(f"/api/cases/{case_id}").json()
    assert detail["analysis"]["assessment"] == "MISSING" and not detail["bulk_eligible"]
    with sessions() as db:
        ids = list(db.scalars(select(EvidenceFile.id).order_by(EvidenceFile.id)))
    assert detail["analysis"]["extracted"]["processed_evidence_ids"] == [ids[0], ids[2]]


def test_all_cases_finish_preprocessing_before_any_ai_call(pipeline, monkeypatch):
    sessions, client, _, background = pipeline
    with sessions() as db:
        ingest(db, workbook([row(), row(code="TEST-002")], {2: [sample()], 3: [sample("DEVICE_ERROR")]}))
    requests = inference(monkeypatch)
    order = []
    actual_preprocess, actual_assess = image_background._preprocess, image_background._assess

    def preprocess(sessions, version_id):
        actual_preprocess(sessions, version_id)
        order.append("privacy_done")

    def assess(sessions, payload):
        order.append("ai")
        actual_assess(sessions, payload)

    monkeypatch.setattr(image_background, "_preprocess", preprocess)
    monkeypatch.setattr(image_background, "_assess", assess)
    assert client.post("/api/analysis").json() == {"queued": 2}
    background.finish()
    assert order == ["privacy_done", "privacy_done", "ai", "ai"] and len(requests) == 2


def test_tampered_artifact_never_reaches_model(pipeline, monkeypatch):
    sessions, client, _, background = pipeline
    add_case(sessions, [sample()])
    requests = inference(monkeypatch)
    actual = image_background._inputs

    def tamper(sessions, batch):
        result = actual(sessions, batch)
        with sessions() as db:
            record = db.scalar(select(EvidencePrivacy))
            from app.services.storage import get_storage

            get_storage().write(record.sanitized_path, sample())
        return result

    monkeypatch.setattr(image_background, "_inputs", tamper)
    client.post("/api/analysis")
    background.finish()
    assert requests == []
    with sessions() as db:
        assert db.scalar(select(AnalysisResult)).status == "FAILED"
        assert db.scalar(select(EvidencePrivacy)).status == "INVALID"


def test_config_change_between_phases_blocks_ai_and_can_be_reprocessed(pipeline, monkeypatch):
    sessions, client, path, background = pipeline
    case_id = add_case(sessions, [sample()])
    requests = inference(monkeypatch)
    actual = image_background._inputs

    def change(sessions, batch):
        result = actual(sessions, batch)
        path.write_text(ProfileSet().model_dump_json())
        return result

    monkeypatch.setattr(image_background, "_inputs", change)
    client.post("/api/analysis")
    background.finish()
    assert requests == []
    detail = client.get(f"/api/cases/{case_id}").json()
    assert detail["analysis"]["status"] == "FAILED"
    assert not detail["versions"][0]["evidence"][0]["privacy"]["vlm_allowed"]
    monkeypatch.setattr(image_background, "_inputs", actual)
    client.post(f"/api/cases/{case_id}/reanalyze")
    background.finish()
    assert requests == []
    assert client.get(f"/api/cases/{case_id}").json()["analysis"]["status"] == "MANUAL_REVIEW"


def test_preprocessing_only_runs_without_requesting_ai(pipeline, monkeypatch):
    sessions, client, _, background = pipeline
    add_case(sessions, [sample()])
    requests = inference(monkeypatch)
    client.post("/api/privacy/preprocess")
    assert background.batches[0][0].analyze is False
    background.finish()
    assert requests == []
    with sessions() as db:
        assert db.scalar(select(AnalysisResult)).status == "NOT_STARTED"
        assert db.scalar(select(EvidencePrivacy)).status == "READY"


def test_background_failure_blocks_whole_batch_and_manual_retry_recovers(pipeline, monkeypatch):
    sessions, client, _, background = pipeline
    add_case(sessions, [sample()])
    requests = inference(monkeypatch)
    actual = image_background._preprocess

    def fail(*args):
        raise OSError("private source path")

    monkeypatch.setattr(image_background, "_preprocess", fail)
    client.post("/api/analysis")
    background.finish()
    assert requests == []
    with sessions() as db:
        assert db.scalar(select(AnalysisResult)).status == "FAILED"
        assert db.scalar(select(EvidencePrivacy)).status == "ERROR"
        assert "private source path" not in db.scalar(select(AnalysisResult)).error
    monkeypatch.setattr(image_background, "_preprocess", actual)
    assert client.post("/api/analysis").json() == {"queued": 1}
    background.finish()
    assert len(requests) == 1


def test_email_import_submits_direct_background_work_after_commit(pipeline, monkeypatch):
    sessions, _, _, background = pipeline
    with sessions() as db:
        synchronize(db, Provider(workbook([row()], {2: [sample()]})))
        db.commit()

    def capture(db, batch, background_tasks=None):
        background.batches.append((batch, sessionmaker(bind=db.get_bind(), expire_on_commit=False)))

    monkeypatch.setattr(image_background, "defer", capture)
    assert worker.run_one(sessions)
    assert len(background.batches) == 1 and not background.batches[0][0].analyze
    background.finish()
    with sessions() as db:
        assert db.scalar(select(EvidencePrivacy)).status == "READY"
        assert db.scalar(select(AnalysisResult)).status == "NOT_STARTED"
        assert not list(db.scalars(select(ProcessingJob).where(ProcessingJob.kind == "PREPROCESS_EVIDENCE")))


def test_legacy_queued_analysis_uses_current_preprocessing_before_vlm(pipeline, monkeypatch):
    sessions, _, _, background = pipeline
    case_id = add_case(sessions, [sample()])
    with sessions() as db:
        for job in db.scalars(select(ProcessingJob)):
            job.status = "DONE"
        version_id = db.get(AttendanceCase, case_id).active_version_id
        db.add(ProcessingJob(kind="ANALYZE", key="legacy-analysis", payload={"version_id": version_id}))
        db.commit()
    requests = inference(monkeypatch)
    monkeypatch.setattr(image_background, "defer", lambda db, batch: background.batches.append((batch, sessions)))
    assert worker.run_one(sessions)
    assert not requests
    assert len(background.batches) == 1 and background.batches[0][0].analyze
    background.finish()
    assert len(requests) == 1
    with sessions() as db:
        assert db.scalar(select(EvidencePrivacy)).status == "READY"
        assert db.scalar(select(AnalysisResult)).status == "COMPLETED"


def test_duplicate_delivery_does_not_call_model_twice(pipeline, monkeypatch):
    sessions, client, _, background = pipeline
    add_case(sessions, [sample()])
    requests = inference(monkeypatch)
    actual, payloads = image_background._inputs, []

    def capture(sessions, batch):
        result = actual(sessions, batch)
        payloads.extend(result)
        return result

    monkeypatch.setattr(image_background, "_inputs", capture)
    client.post("/api/analysis")
    background.finish()
    with sessions() as db:
        analysis.analyze(db, payloads[0]["version_id"], privacy_payload=payloads[0])
        db.commit()
    assert len(requests) == 1


@pytest.mark.parametrize(
    "refs,category", [([], "DEVICE_ERROR"), ([1, 1], "DEVICE_ERROR"), ([2], "DEVICE_ERROR"), ([1], "MADE_UP")]
)
def test_invalid_model_output_requires_manual_action(pipeline, monkeypatch, refs, category):
    sessions, client, _, background = pipeline
    case_id = add_case(sessions, [sample()])
    requests = inference(monkeypatch, refs=refs, category=category)
    client.post("/api/analysis")
    background.finish()
    detail = client.get(f"/api/cases/{case_id}").json()
    assert len(requests) == 1 and detail["analysis"]["status"] == "FAILED"
    assert not detail["bulk_eligible"]


def test_no_direct_or_empty_input_can_skip_preprocessing(pipeline, monkeypatch):
    sessions, _, _, _ = pipeline
    add_case(sessions, [sample()])
    requests = inference(monkeypatch)
    with sessions() as db:
        version_id = db.scalar(select(AnalysisResult.version_id))
        with pytest.raises(ValueError, match="completed background"):
            analysis.analyze(db, version_id)
        with pytest.raises(ValidationError):
            analysis.analyze(db, version_id, privacy_payload={})
    assert requests == []


def test_profile_revocation_blocks_old_bulk_eligibility(pipeline, monkeypatch):
    sessions, client, path, background = pipeline
    case_id = add_case(sessions, [sample()])
    inference(monkeypatch)
    client.post("/api/analysis")
    background.finish()
    assert client.get(f"/api/cases/{case_id}").json()["bulk_eligible"]
    path.write_text(ProfileSet().model_dump_json())
    assert not client.get(f"/api/cases/{case_id}").json()["bulk_eligible"]


def test_bulk_review_is_atomic_and_accepts_only_processed_visual_results(pipeline, monkeypatch):
    sessions, client, _, background = pipeline
    buffer = BytesIO()
    Image.new("RGB", (90, 90), "white").save(buffer, format="PNG")
    with sessions() as db:
        ingest(db, workbook([row("SAFE"), row("MANUAL")], {2: [sample()], 3: [buffer.getvalue()]}))
        ids = list(db.scalars(select(AttendanceCase.id).order_by(AttendanceCase.id)))
        db.commit()
    requests = inference(monkeypatch)
    client.post("/api/analysis")
    background.finish()
    assert len(requests) == 1
    assert client.post("/api/cases/bulk-confirm", json={"ids": ids, "acknowledged": True}).status_code == 409
    assert all(client.get(f"/api/cases/{case_id}").json()["hr_status"] == "PENDING_REVIEW" for case_id in ids)
    assert client.post("/api/cases/bulk-confirm", json={"ids": [ids[0]], "acknowledged": True}).status_code == 200
    assert client.get(f"/api/cases/{ids[0]}").json()["hr_status"] == "CONFIRMED"
    assert client.get(f"/api/cases/{ids[1]}").json()["hr_status"] == "PENDING_REVIEW"


def test_preprocessing_endpoint_requires_authentication(pipeline):
    _, client, _, _ = pipeline
    client.post("/api/auth/logout")
    assert client.post("/api/privacy/preprocess").status_code == 401


def test_assessment_input_rejects_original_paths():
    with pytest.raises(ValidationError):
        AssessmentRequest.model_validate(
            {
                "schema_version": 1,
                "version_id": 1,
                "privacy_request_id": "a" * 32,
                "privacy_revision": "b" * 64,
                "images": [{"evidence_id": 1, "artifact": "/private/source.png", "sha256": "c" * 64}],
            }
        )


def test_real_fastapi_background_task_completes_without_worker_or_queue(pipeline, monkeypatch):
    sessions, client, _, background = pipeline
    case_id = add_case(sessions, [sample()])
    requests = inference(monkeypatch)
    monkeypatch.setattr(image_background, "run_batch", background.run)
    # TestClient awaits response background tasks, unlike a network client receiving
    # the response body. This exercises the real FastAPI-to-async adapter.
    assert client.post("/api/analysis").json() == {"queued": 1}
    assert len(requests) == 1
    assert client.get(f"/api/cases/{case_id}").json()["analysis"]["status"] == "COMPLETED"
    with sessions() as db:
        assert not list(db.scalars(select(ProcessingJob).where(ProcessingJob.kind == "ANALYZE")))


def test_application_background_offloads_image_work_from_event_loop(pipeline, monkeypatch):
    import threading

    sessions, _, _, background = pipeline
    add_case(sessions, [sample()])
    with sessions() as db:
        batch = plan_batch(db, [db.scalar(select(AnalysisResult.version_id))])
        db.commit()
    entered, release = threading.Event(), threading.Event()
    thread_ids = []
    actual = image_background._preprocess

    def blocking(sessions, version_id):
        thread_ids.append(threading.get_ident())
        entered.set()
        assert release.wait(timeout=2)
        actual(sessions, version_id)

    monkeypatch.setattr(image_background, "_preprocess", blocking)

    async def scenario():
        task = asyncio.create_task(background.run(batch, sessions))
        try:
            assert await asyncio.to_thread(entered.wait, 1)
            await asyncio.sleep(0)
            assert not task.done() and thread_ids[0] != threading.get_ident()
        finally:
            release.set()
        await task

    asyncio.run(scenario())
    with sessions() as db:
        assert db.scalar(select(EvidencePrivacy)).status == "READY"


def test_interrupted_background_can_restart_without_releasing_old_run(pipeline, monkeypatch):
    sessions, client, _, background = pipeline
    case_id = add_case(sessions, [sample()])
    requests = inference(monkeypatch)
    client.post("/api/analysis")
    assert client.post(f"/api/cases/{case_id}/reanalyze").status_code == 409
    assert client.post(f"/api/cases/{case_id}/reanalyze?restart_background=true").status_code == 200
    assert len(background.batches) == 2
    background.finish()
    assert len(requests) == 1  # The superseded batch may sanitize, but never infer.
