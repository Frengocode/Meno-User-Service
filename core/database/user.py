from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from config.config import settings


engine = create_async_engine(settings.PG_URL.get_secret_value())

session_factory = async_sessionmaker(class_=AsyncSession, bind=engine)


class Base(DeclarativeBase):
    pass
