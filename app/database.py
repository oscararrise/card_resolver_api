import os
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


class Base(DeclarativeBase):
    pass


class Batch(Base):
    __tablename__ = "batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    status: Mapped[str] = mapped_column(String(20), default="staged")
    rows_read: Mapped[int] = mapped_column(Integer)
    loaded: Mapped[int] = mapped_column(Integer)
    skipped: Mapped[int] = mapped_column(Integer)
    errors: Mapped[int] = mapped_column(Integer)
    warnings: Mapped[int] = mapped_column(Integer)
    cards_count: Mapped[int] = mapped_column(Integer)
    issues: Mapped[list["Issue"]] = relationship(cascade="all, delete-orphan")


class Credential(Base):
    __tablename__ = "credentials"
    __table_args__ = (UniqueConstraint("batch_id", "source_row", "source", name="uq_source_row"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"), index=True)
    source_row: Mapped[int] = mapped_column(Integer)
    eid: Mapped[str] = mapped_column(String(80))
    full_name: Mapped[str] = mapped_column(String(255))
    facility_code: Mapped[int] = mapped_column(Integer)
    card_number: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(16))


class Issue(Base):
    __tablename__ = "issues"
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"), index=True)
    source_row: Mapped[int] = mapped_column(Integer)
    level: Mapped[str] = mapped_column(String(10))
    code: Mapped[str] = mapped_column(String(50))
    detail: Mapped[str] = mapped_column(Text)


class Active(Base):
    __tablename__ = "active_dataset"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"))


def make_session(url=None):
    engine = create_engine(url or os.getenv("DATABASE_URL", "sqlite:///./card_resolver.db"), pool_pre_ping=True)
    return engine, sessionmaker(engine, expire_on_commit=False)
