"""Evaluate against a separate synthetic answer key; never a classifier input."""

import json
from collections import defaultdict

from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import AnalysisResult, AttendanceCase


def run():
    answers = json.loads((settings.storage_dir / "demo" / "answers.json").read_text())
    groups = defaultdict(lambda: {"total": 0, "correct": 0})
    with SessionLocal() as db:
        rows = db.execute(
            select(AttendanceCase, AnalysisResult).join(
                AnalysisResult, AnalysisResult.version_id == AttendanceCase.active_version_id
            )
        ).all()
        for case, result in rows:
            if case.code not in answers:
                continue
            answer = answers[case.code]
            group = groups[answer["group"]]
            group["total"] += 1
            group["correct"] += result.category == answer["category"] and result.status == "COMPLETED"
    report = {
        "scope": "SYNTHETIC DATA - these results do not establish accuracy on real hospital data",
        "classification_only": True,
        "groups": dict(sorted(groups.items())),
        "total": sum(g["total"] for g in groups.values()),
        "correct": sum(g["correct"] for g in groups.values()),
    }
    path = settings.storage_dir / "demo" / "evaluation.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    run()
