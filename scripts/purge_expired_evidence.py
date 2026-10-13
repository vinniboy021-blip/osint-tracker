"""Delete expired evidence objects and rows; run from a scheduled maintenance job."""
from datetime import UTC, datetime
from app.db import SessionLocal
from app.evidence import LocalStorage
from app.models import Evidence, EvidenceVersion
from app.config import settings

def main() -> None:
    deleted = 0
    storage = LocalStorage(settings.evidence_path)
    with SessionLocal() as db:
        rows = db.query(Evidence).filter(Evidence.retention_until.is_not(None), Evidence.retention_until <= datetime.now(UTC)).all()
        for evidence in rows:
            keys = [evidence.storage_key] + [v.storage_key for v in db.query(EvidenceVersion).filter(EvidenceVersion.evidence_id == evidence.id)]
            for key in keys:
                try: storage.delete(key)
                except ValueError: pass
            db.delete(evidence); deleted += 1
        db.commit()
    print(f"expired_evidence_deleted={deleted}")

if __name__ == "__main__": main()
