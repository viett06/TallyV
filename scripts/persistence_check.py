"""Compare business state and evidence bytes across a real application restart."""

import argparse
import hashlib
import json

import httpx

from app.core.config import settings


def snapshot():
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=30, trust_env=False) as client:
        client.post(
            "/api/auth/login", json={"username": settings.demo_username, "password": settings.demo_password}
        ).raise_for_status()
        rows = client.get("/api/cases?page_size=100&source=all").json()["items"]
        rows.sort(key=lambda row: row["id"])
        emails = client.get("/api/emails?source=all").json()
        detail = client.get("/api/cases/" + str(rows[0]["id"])).json()
        image = detail["versions"][0]["evidence"][0]
        evidence = client.get(image["url"])
        evidence.raise_for_status()
        jobs = client.get("/api/jobs").json()
        return {
            "cases": [
                {
                    k: row[k]
                    for k in [
                        "id",
                        "code",
                        "active_version_id",
                        "hr_status",
                        "hr_category",
                        "hr_note",
                        "confirmed_at",
                        "confirmed_by",
                    ]
                }
                for row in rows
            ],
            "emails": sorted(
                [{k: e[k] for k in ["id", "source_id", "status", "row_count", "error_count"]} for e in emails],
                key=lambda row: row["id"],
            ),
            "evidence_sha256": hashlib.sha256(evidence.content).hexdigest(),
            "audit": detail["audit"],
            "jobs": sorted(
                [{k: j[k] for k in ["id", "kind", "status", "attempts"]} for j in jobs if j["kind"] != "SYNC"],
                key=lambda row: row["id"],
            ),
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["before", "after"])
    args = parser.parse_args()
    root = settings.storage_dir / "demo"
    root.mkdir(parents=True, exist_ok=True)
    path = root / "persistence-before.json"
    data = snapshot()
    if args.phase == "before":
        path.write_text(json.dumps(data, ensure_ascii=False))
        print({"snapshot": "saved", "cases": len(data["cases"]), "emails": len(data["emails"])})
    else:
        original = json.loads(path.read_text())
        assert data == original, "Business state, evidence or durable job status changed across restart"
        (root / "persistence.json").write_text(
            json.dumps(
                {
                    "passed": True,
                    "cases": len(data["cases"]),
                    "emails": len(data["emails"]),
                    "file_hash_unchanged": True,
                    "audit_unchanged": True,
                    "jobs_unchanged": True,
                }
            )
        )
        print(
            {
                "persistence": "passed",
                "cases": len(data["cases"]),
                "emails": len(data["emails"]),
                "file_hash_unchanged": True,
                "audit_unchanged": True,
                "jobs_unchanged": True,
            }
        )
