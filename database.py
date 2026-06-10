# database.py — PGB Prospecting DB layer
import os
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Integer, String, Text, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Railway injecte postgresql://, asyncpg requiert postgresql+asyncpg://
_db_url = os.getenv("DATABASE_URL", "")
if _db_url.startswith("postgresql://"):
    _db_url = _db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(_db_url, echo=False) if _db_url else None
AsyncSessionLocal: async_sessionmaker[AsyncSession] | None = (
    async_sessionmaker(engine, expire_on_commit=False) if engine else None
)


class Base(DeclarativeBase):
    pass


class DBSession(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    ts: Mapped[int] = mapped_column(BigInteger)
    date_fr: Mapped[str] = mapped_column(String(20))
    service: Mapped[str] = mapped_column(Text)
    region: Mapped[str] = mapped_column(String(100))
    campaign_name: Mapped[str] = mapped_column(Text)
    icp: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    prospects: Mapped[list["DBProspect"]] = relationship(
        "DBProspect",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="DBProspect.idx",
    )


class DBProspect(Base):
    __tablename__ = "prospects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sessions.id", ondelete="CASCADE")
    )
    idx: Mapped[int] = mapped_column(Integer)
    data: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), default="waiting")
    note: Mapped[str] = mapped_column(Text, default="")

    session: Mapped["DBSession"] = relationship("DBSession", back_populates="prospects")


async def init_db() -> None:
    """Crée les tables si elles n'existent pas. No-op si DATABASE_URL n'est pas défini."""
    if not engine:
        return
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("✓ Database tables ready")
    except Exception as e:
        print(f"WARNING: DB unavailable at startup ({e}) — running without persistence")
