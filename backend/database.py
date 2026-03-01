"""SQLite engine and session management."""

from sqlmodel import SQLModel, Session, create_engine

from backend.config import settings

engine = create_engine(
    f"sqlite:///{settings.db_path}",
    echo=False,
    connect_args={"check_same_thread": False},
)


def create_db_and_tables() -> None:
    """Create all tables defined in SQLModel metadata."""
    SQLModel.metadata.create_all(engine)


def get_session():
    """FastAPI dependency: yields a database session per request."""
    with Session(engine) as session:
        yield session
