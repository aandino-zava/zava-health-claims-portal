import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError

from app.database import Claim
from app.telemetry import event

TRANSITIONS = {
    "Submitted": ["Under Review"],
    "Under Review": ["Pending Info", "Approved", "Denied"],
    "Pending Info": ["Under Review"],
    "Denied": ["In Appeal"],
    "In Appeal": ["Under Review"],
    "Approved": [],
}


def utcnow():
    return datetime.now(UTC)


def utc_iso(value):
    # SQLite drops timezone metadata; all writes in this application use UTC.
    return value.replace(tzinfo=UTC).isoformat() if value.tzinfo is None else value.astimezone(UTC).isoformat()


def summary(row):
    return {
        "id": row.id,
        "patient_id": row.patient_id,
        "patient_name": row.patient_name,
        "service_type": row.service_type,
        "status": row.status,
        "amount": f"{row.amount_cents / 100:.2f}",
        "service_date": row.payload["service_date"],
        "provider_name": row.payload["provider_name"],
        "created_at": utc_iso(row.created_at),
        "version": row.version,
    }


def detail(row):
    return {**summary(row), "data": row.payload, "history": row.history}


def get_claim(db, claim_id):
    row = db.get(Claim, claim_id)
    if not row:
        raise HTTPException(404, "Claim not found")
    return row


def list_claims(db, q, status, service_type, offset, limit):
    conditions = []
    if q:
        # Escape wildcard characters so the search behaves as literal text.
        pattern = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        conditions.append(
            or_(
                *(
                    col.ilike(pattern, escape="\\")
                    for col in (
                        Claim.id,
                        Claim.patient_id,
                        Claim.patient_name,
                    )
                )
            )
        )
    if status:
        conditions.append(Claim.status == status)
    if service_type:
        conditions.append(Claim.service_type == service_type)
    count = db.scalar(select(func.count()).select_from(Claim).where(*conditions))
    rows = db.scalars(
        select(Claim)
        .where(*conditions)
        .order_by(Claim.created_at.desc(), Claim.id)
        .offset(offset)
        .limit(limit)
    ).all()
    return {"items": [summary(row) for row in rows], "total": count, "offset": offset, "limit": limit}


def create_claim(db, data, actor, key):
    payload = data.model_dump(mode="json")
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    request_key = hashlib.sha256(f"{actor}:{key}".encode()).hexdigest()
    old = db.scalar(select(Claim).where(Claim.request_key == request_key))
    if old:
        if old.request_hash != digest:
            raise HTTPException(409, "Idempotency key already used with different claim data")
        return old, False
    now = utcnow()
    row = Claim(
        id=f"CLM-{now.year}-{uuid4().hex[:16].upper()}",
        patient_id=data.patient_id,
        patient_name=f"{data.first_name} {data.last_name}",
        service_type=data.service_type,
        status="Submitted",
        amount_cents=int(data.amount * 100),
        created_at=now,
        updated_at=now,
        version=1,
        payload=payload,
        created_by=actor,
        request_key=request_key,
        request_hash=digest,
        history=[
            {
                "status": "Submitted",
                "at": now.isoformat(),
                "actor": actor,
                "note": "Synthetic claim submitted",
            }
        ],
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        old = db.scalar(select(Claim).where(Claim.request_key == request_key))
        if old and old.request_hash == digest:
            return old, False
        if old:
            raise HTTPException(409, "Idempotency key conflict") from None
        raise
    event("claim_created")
    return row, True


def change_status(db, claim_id, data, actor):
    row = get_claim(db, claim_id)
    if row.version != data.expected_version:
        raise HTTPException(409, "Claim changed; refresh and retry")
    if data.status not in TRANSITIONS[row.status]:
        raise HTTPException(409, "Invalid status transition")
    now = utcnow()
    history = row.history + [
        {"status": data.status, "at": now.isoformat(), "actor": actor, "note": data.note}
    ]
    changed = db.execute(
        update(Claim)
        .where(Claim.id == claim_id, Claim.version == data.expected_version)
        .values(status=data.status, version=data.expected_version + 1, updated_at=now, history=history)
    )
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Claim changed; refresh and retry")
    db.commit()
    db.expire_all()
    event("claim_status_changed", status=data.status)
    return get_claim(db, claim_id)


def analytics(db):
    # Aggregate in SQL; no patient-level data in analytics responses.
    stats = db.execute(
        select(Claim.status, func.count(), func.sum(Claim.amount_cents)).group_by(Claim.status)
    ).all()
    status_counts = {name: 0 for name in TRANSITIONS}
    status_amounts = {name: 0 for name in TRANSITIONS}
    for name, count, amount in stats:
        status_counts[name] = count
        status_amounts[name] = amount
    total = sum(status_counts.values())
    cents = sum(status_amounts.values())
    by_service = db.execute(select(Claim.service_type, func.count()).group_by(Claim.service_type)).all()
    # JSON scalar expressions work on SQLite and PostgreSQL.
    provider = Claim.payload["provider_name"].as_string()
    by_provider = db.execute(
        select(provider, func.sum(Claim.amount_cents))
        .group_by(provider)
        .order_by(func.sum(Claim.amount_cents).desc())
        .limit(10)
    ).all()
    month = func.substr(Claim.payload["service_date"].as_string(), 1, 7)
    by_month = db.execute(select(month, func.count()).group_by(month).order_by(month)).all()
    this_month = utcnow().strftime("%Y-%m")
    return {
        "total": total,
        "total_amount": cents / 100,
        "approved_amount": status_amounts["Approved"] / 100,
        "denied_amount": status_amounts["Denied"] / 100,
        "approval_rate": round(status_counts["Approved"] * 100 / total) if total else 0,
        "average_amount": round(cents / total / 100, 2) if total else 0,
        "this_month": next((count for name, count in by_month if name == this_month), 0),
        "by_status": status_counts,
        "by_service": dict(by_service),
        "by_month": dict(by_month),
        "by_provider": {name: amount / 100 for name, amount in by_provider},
    }
