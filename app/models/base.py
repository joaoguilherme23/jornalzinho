"""Base declarativa compartilhada pelos modelos persistentes do Jornalzinho."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base dos modelos SQLAlchemy 2.0."""
