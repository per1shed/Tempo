from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    settings: Mapped["UserSettings"] = relationship(
        "UserSettings", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    weight_logs: Mapped[list["WeightLog"]] = relationship(
        "WeightLog", back_populates="user", cascade="all, delete-orphan"
    )
    block_logs: Mapped[list["BlockLog"]] = relationship(
        "BlockLog", back_populates="user", cascade="all, delete-orphan"
    )
    stopwatch: Mapped[Optional["StopwatchState"]] = relationship(
        "StopwatchState",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )


class UserSettings(Base):
    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    # auto = по сезону; term = учёба; holiday = каникулы
    calendar_mode: Mapped[str] = mapped_column(String(16), default="auto", nullable=False)
    pushes_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    quiet_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    height_cm: Mapped[int] = mapped_column(Integer, default=178, nullable=False)
    weight_goal_min: Mapped[float] = mapped_column(Float, default=80.0, nullable=False)
    weight_goal_max: Mapped[float] = mapped_column(Float, default=85.0, nullable=False)
    ai_mode: Mapped[str] = mapped_column(String(16), default="coach", nullable=False)
    # Последнее сообщение с inline-клавиатурой (только оно может иметь кнопки)
    last_kb_message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    last_block_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship("User", back_populates="settings")


class WeightLog(Base):
    __tablename__ = "weight_logs"
    __table_args__ = (UniqueConstraint("user_id", "logged_on", name="uq_weight_user_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    weight_kg: Mapped[float] = mapped_column(Float, nullable=False)
    logged_on: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship("User", back_populates="weight_logs")


class BlockLog(Base):
    """Отметка продуктивного блока (для % продуктивности)."""

    __tablename__ = "block_logs"
    __table_args__ = (
        UniqueConstraint("user_id", "day", "block_key", name="uq_block_user_day_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    day: Mapped[date] = mapped_column(Date, nullable=False)
    block_key: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="done", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship("User", back_populates="block_logs")


class StopwatchState(Base):
    """Состояние секундомера пользователя (один на user)."""

    __tablename__ = "stopwatch_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    # idle | running | paused
    status: Mapped[str] = mapped_column(String(16), default="idle", nullable=False)
    segment_started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    elapsed_before: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    laps_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship("User", back_populates="stopwatch")


class MotivationQuote(Base):
    """Пул мотивационных цитат для fallback и ротации."""

    __tablename__ = "motivation_quotes"
    __table_args__ = (
        UniqueConstraint("text_hash", name="uq_motivation_quotes_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # morning | hourly | rest
    kind: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    theme: Mapped[str] = mapped_column(String(32), default="general", nullable=False, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # seed | ai | ai_saved
    source: Mapped[str] = mapped_column(String(16), default="seed", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    use_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
