from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import AsyncContextManager, AsyncGenerator
from core.database.user import session_factory
from services.user.models import User
from services.user.scheme import SUser
from redis.asyncio import StrictRedis
from config.config import settings
from jose import jwt
from typing import Annotated
import json

oauth2_password_bearer = OAuth2PasswordBearer(
    "http://localhost:8081/auth-service/api/v1/auth/login/"
)


async def get_session() -> AsyncGenerator[AsyncContextManager, AsyncSession]:
    async with session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_redis():
    return await StrictRedis(host=settings.REDIS_HOST, port=settings.REDIS_PORT)


async def get_current_user(
    token: Annotated[str, Depends(oauth2_password_bearer)],
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[StrictRedis, Depends(get_redis)],
):
    payload = jwt.decode(token, settings.AUTH_SECRET_KEY.get_secret_value())
    user_id: int = payload.get("sub")
    if not user_id:
        raise HTTPException(detail="User id is null", status_code=400)

    cached_data = await redis.get(f"get-current-user-{user_id}")
    if cached_data:
        return SUser(**json.loads(cached_data))

    stmt = select(User).filter_by(id=int(user_id))
    result = await session.execute(stmt)
    user = result.scalars().first()

    if not user:
        raise HTTPException(detail="User not found", status_code=404)

    response = SUser(**user.__dict__)
    await redis.setex(f"get-current-user-{user_id}", 5000, json.dumps(response.dict()))
    return response
