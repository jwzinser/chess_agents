"""
SQLite persistence for users, games and move history.

Single small VM, single uvicorn process (no --workers): a plain
SQLAlchemy sync engine talking to a local SQLite file is enough, no async
driver or migration framework needed at this size.
"""

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

DB_PATH = os.environ.get("CHESS_DB_PATH", str(Path(__file__).parent / "chess.db"))

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

AI_USER_ID = "ai"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    picture: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_now)


class Game(Base):
    __tablename__ = "games"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: uuid.uuid4().hex)
    mode: Mapped[str] = mapped_column(String)  # "ai" | "pvp"
    white_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    black_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    fen: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="in_progress")
    result: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)


class Move(Base):
    __tablename__ = "moves"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id"))
    ply: Mapped[int] = mapped_column(Integer)
    uci: Mapped[str] = mapped_column(String)
    san: Mapped[str] = mapped_column(String)
    color: Mapped[str] = mapped_column(String)  # "white" | "black"
    created_at: Mapped[datetime] = mapped_column(default=_now)


def init_db() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        if session.get(User, AI_USER_ID) is None:
            session.add(User(id=AI_USER_ID, name="AI", email=None, picture=None))
            session.commit()


def upsert_user(
    session: Session, sub: str, email: str | None, name: str | None, picture: str | None
) -> User:
    user = session.get(User, sub)
    if user is None:
        user = User(id=sub, email=email, name=name, picture=picture)
        session.add(user)
    else:
        user.email = email
        user.name = name
        user.picture = picture
    session.commit()
    return user
