import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _uuid_col():
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Distributor(Base):
    __tablename__ = "distributors"

    id: Mapped[uuid.UUID] = _uuid_col()
    name: Mapped[str] = mapped_column(String)
    region: Mapped[str] = mapped_column(String)
    aum_tier: Mapped[str] = mapped_column(String)
    risk_appetite: Mapped[str] = mapped_column(String)
    preferred_asset_classes: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    relationship_start_date: Mapped[datetime] = mapped_column(DateTime)


class Fund(Base):
    __tablename__ = "funds"

    id: Mapped[uuid.UUID] = _uuid_col()
    name: Mapped[str] = mapped_column(String)
    category: Mapped[str] = mapped_column(String)
    aum: Mapped[float] = mapped_column(Float)
    expense_ratio: Mapped[float] = mapped_column(Float)
    return_1y: Mapped[float] = mapped_column(Float)
    return_3y: Mapped[float] = mapped_column(Float)
    return_5y: Mapped[float] = mapped_column(Float)
    benchmark_name: Mapped[str] = mapped_column(String)
    risk_rating: Mapped[str] = mapped_column(String)
    manager_name: Mapped[str] = mapped_column(String)
    inception_date: Mapped[datetime] = mapped_column(DateTime)


class FundDocument(Base):
    __tablename__ = "fund_documents"

    id: Mapped[uuid.UUID] = _uuid_col()
    fund_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("funds.id"))
    doc_type: Mapped[str] = mapped_column(String)  # factsheet | commentary | brochure
    title: Mapped[str] = mapped_column(String)
    chunk_text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(384))  # all-MiniLM-L6-v2 dim


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = _uuid_col()
    distributor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("distributors.id"))
    rep_id: Mapped[str] = mapped_column(String)
    channel: Mapped[str] = mapped_column(String)  # chat | call
    started_at: Mapped[datetime] = mapped_column(DateTime)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String, default="active")


class ConversationTurn(Base):
    __tablename__ = "conversation_turns"

    id: Mapped[uuid.UUID] = _uuid_col()
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"))
    speaker: Mapped[str] = mapped_column(String)  # rep | distributor
    text: Mapped[str] = mapped_column(Text)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DistributorMemory(Base):
    """Scoped strictly by distributor_id -- every read/write must filter on it."""

    __tablename__ = "distributor_memory"

    id: Mapped[uuid.UUID] = _uuid_col()
    distributor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("distributors.id"), unique=True)
    structured_fields: Mapped[dict] = mapped_column(JSONB, default=dict)
    rolling_summary: Mapped[str] = mapped_column(Text, default="")
    last_updated: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TriggerEvent(Base):
    __tablename__ = "trigger_events"

    id: Mapped[uuid.UUID] = _uuid_col()
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"))
    turn_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversation_turns.id"))
    triggered: Mapped[bool] = mapped_column(Boolean)
    classifier_confidence: Mapped[float] = mapped_column(Float)
    latency_ms: Mapped[int] = mapped_column(Integer)


class FlashCard(Base):
    __tablename__ = "flash_cards"

    id: Mapped[uuid.UUID] = _uuid_col()
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"))
    turn_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversation_turns.id"))
    trigger_reason: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)
    tool_calls_used: Mapped[dict] = mapped_column(JSONB, default=dict)
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    latency_ms: Mapped[int] = mapped_column(Integer)


class EvalSetItem(Base):
    """Hand-labeled, kept separate from live data -- source of truth for regression checks."""

    __tablename__ = "eval_set"

    id: Mapped[uuid.UUID] = _uuid_col()
    conversation_snippet: Mapped[str] = mapped_column(Text)
    expected_trigger: Mapped[bool] = mapped_column(Boolean)
    expected_topic: Mapped[str] = mapped_column(String)
    notes: Mapped[str] = mapped_column(Text, default="")
