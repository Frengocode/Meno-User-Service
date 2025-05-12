from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    declared_attr,
    declarative_mixin,
)
from sqlalchemy import Integer, DateTime
from datetime import datetime


@declarative_mixin
class BaseMixin(DeclarativeBase):
    __abstract__ = True

    id: Mapped[int] = mapped_column(Integer, index=True, primary_key=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow())

    @declared_attr
    def __tablename__(cls) -> str:
        return f"{cls.__name__.lower()}s"
