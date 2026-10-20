"""Explicit, idempotent synthetic seed command: python -m app.seed."""

from datetime import date, timedelta

from app.config import Settings
from app.database import database
from app.schemas import ClaimCreate
from app.services import create_claim, utcnow


def seed(settings=None):
    engine, sessions = database((settings or Settings()).database_url)
    rows = [
        ("Avery", "Demo", "Medical", "Under Review", "1250.00"),
        ("Jordan", "Sample", "Surgical", "Approved", "24500.00"),
        ("Taylor", "Example", "Mental Health", "Pending Info", "350.00"),
        ("Morgan", "Demo", "Medical", "Denied", "890.00"),
        ("Casey", "Sample", "Emergency", "Approved", "8750.00"),
        ("Riley", "Example", "Preventive", "Approved", "475.00"),
        ("Quinn", "Demo", "Dental", "In Appeal", "2100.00"),
        ("Alex", "Sample", "Vision", "Submitted", "310.00"),
    ]
    with sessions() as db:
        for i, (first, last, service, status, amount) in enumerate(rows):
            # Stable seed keys prevent duplicates on repeated container starts.
            payload = ClaimCreate(
                patient_id=f"SYN-{1000 + i}",
                first_name=first,
                last_name=last,
                provider_name=f"Demo Care Center {i % 3 + 1}",
                provider_id=f"DEMO-P{i % 3 + 1}",
                service_type=service,
                service_date=date(2026, 9, 15) - timedelta(days=i * 4),
                diagnosis_code="Z00.00",
                procedure_code="99213",
                amount=amount,
                synthetic_data_confirmed=True,
            )
            row, created = create_claim(db, payload, "synthetic-seed", f"seed-{i:04}")
            if created and status != "Submitted":
                path = ["Under Review"]
                if status == "In Appeal":
                    path += ["Denied", "In Appeal"]
                elif status != "Under Review":
                    path += [status]
                for step in path:
                    row.history = row.history + [
                        {
                            "status": step,
                            "at": utcnow().isoformat(),
                            "actor": "synthetic-seed",
                            "note": "Synthetic demonstration history",
                        }
                    ]
                row.status = status
                row.version += len(path)
                db.commit()
    engine.dispose()


if __name__ == "__main__":
    seed()
