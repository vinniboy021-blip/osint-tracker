#!/usr/bin/env python3
"""Delete expired evidence objects and rows; run from a scheduled maintenance job."""
import sys
from datetime import UTC, datetime

from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.evidence import LocalStorage
from app.models import Evidence, EvidenceVersion


def main() -> None:
    deleted = 0
    errors = 0
    storage = LocalStorage(settings.evidence_path)
    now = datetime.now(UTC)

    with SessionLocal() as db:
        stmt = select(Evidence).where(
            Evidence.retention_until.is_not(None),
            Evidence.retention_until <= now,
        )
        rows = db.scalars(stmt).all()

        for evidence in rows:
            version_keys = db.scalars(
                select(EvidenceVersion.storage_key).where(
                    EvidenceVersion.evidence_id == evidence.id
                )
            ).all()
            keys = [evidence.storage_key, *version_keys]
            for key in keys:
                try:
                    storage.delete(key)
                except ValueError:
                    errors += 1
            db.delete(evidence)
            deleted += 1

        db.commit()

    print(f"expired_evidence_deleted={deleted} errors={errors}")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
