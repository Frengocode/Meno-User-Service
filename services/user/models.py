from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Boolean, UUID
from core.database.user import Base
from mixins.mixins import BaseMixin
import uuid


class User(Base, BaseMixin):

    username: Mapped[str] = mapped_column(String, nullable=False)
    password: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=True)
    picture_url: Mapped[str] = mapped_column(String, nullable=True)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    token: Mapped[uuid.uuid4] = mapped_column(UUID, default=uuid.uuid4())
