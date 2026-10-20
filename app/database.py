from sqlalchemy import JSON, Column, DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


class Claim(Base):
    __tablename__ = "claims"
    id = Column(String(50), primary_key=True)
    patient_id = Column(String(50), nullable=False, index=True)
    patient_name = Column(String(160), nullable=False, index=True)
    service_type = Column(String(40), nullable=False, index=True)
    status = Column(String(40), nullable=False, index=True)
    amount_cents = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    payload = Column(JSON, nullable=False)
    history = Column(JSON, nullable=False)
    request_key = Column(String(250), unique=True, nullable=True)
    request_hash = Column(String(64), nullable=True)
    created_by = Column(Text, nullable=False)


def database(url):
    options = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=options, pool_pre_ping=True, hide_parameters=True)
    return engine, sessionmaker(engine, expire_on_commit=False)
