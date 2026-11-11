"""Manage the permitted reference images for attendance evidence."""

from argparse import ArgumentParser

from app.db.session import SessionLocal
from app.models import EvidenceReference, EvidenceViewpoint
from app.services.evidence_history import active_evidence, index_reference
from app.services.storage import read_bytes


def main() -> int:
    parser = ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("index", "exclude"):
        subparsers.add_parser(command).add_argument("evidence_ids", type=int, nargs="+")
    label = subparsers.add_parser("label")
    label.add_argument("evidence_id", type=int)
    label.add_argument("--location", required=True)
    label.add_argument("--basis", required=True)
    args = parser.parse_args()
    with SessionLocal() as db:
        if args.command == "label":
            reference = db.get(EvidenceReference, args.evidence_id)
            group = db.get(EvidenceViewpoint, reference.viewpoint_id) if reference and reference.viewpoint_id else None
            if not group or reference.excluded or active_evidence(db, args.evidence_id, confirmed_only=True) is None:
                parser.error("The label requires an active, indexed reference with a viewpoint")
            location, basis = args.location.strip(), args.basis.strip()
            if not 0 < len(location) <= 160 or not 0 < len(basis) <= 320:
                parser.error("Location and basis must contain 1–160 and 1–320 characters respectively")
            group.location, group.location_basis, group.location_evidence_id = location, basis, args.evidence_id
            db.commit()
            print(f"Viewpoint {group.id} labeled using evidence {args.evidence_id}")
            return 0

        failed = False
        for evidence_id in dict.fromkeys(args.evidence_ids):
            if args.command == "exclude":
                reference = db.get(EvidenceReference, evidence_id)
                if reference is None:
                    if active_evidence(db, evidence_id) is None:
                        print(f"Evidence {evidence_id}: unavailable")
                        failed = True
                        continue
                    reference = EvidenceReference(evidence_id=evidence_id)
                    db.add(reference)
                reference.excluded, reference.embedding, reference.fingerprint = True, None, b""
                reference.model, reference.viewpoint_id = "", None
                db.commit()
                print(f"Evidence {evidence_id}: excluded")
                continue
            evidence = active_evidence(db, evidence_id, confirmed_only=True)
            if evidence is None:
                print(f"Evidence {evidence_id}: requires an active HR-confirmed case")
                failed = True
                continue
            try:
                outcome = index_reference(db, evidence, read_bytes(evidence.path))
                db.commit()
            except Exception as error:
                db.rollback()
                print(f"Evidence {evidence_id}: indexing unavailable ({type(error).__name__})")
                failed = True
                continue
            failed |= outcome["status"] in {"UNAVAILABLE", "OUT_OF_SCOPE"}
            print(f"Evidence {evidence_id}: {outcome['status']}, viewpoint {outcome.get('viewpoint_id', '—')}")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
