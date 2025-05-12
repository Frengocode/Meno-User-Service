from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from services.user.service import UserService
from services.user.scheme import (
    SUser,
    SCreateUserRequest,
    SCreateUserResponse,
    SUpdateUserRequest,
    SUpdateUserResponse,
    SUpdatePasswordResponse,
    SUpdatePasswordRequest,
    SResetPasswordRequest,
)
from core.dependcies.dependcies import get_session, get_redis, get_current_user
from typing import Annotated
from redis.asyncio import StrictRedis


user_service_router = APIRouter(
    tags=["User Service API v1"], prefix="/user-service/api/v1"
)


@user_service_router.post(
    "/create-user/",
    response_model=SCreateUserResponse,
    status_code=201,
    dependencies=[Depends(get_session)],
)
async def create_account(
    request: SCreateUserRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    service = UserService(session=session)
    return await service.create_user(request)


@user_service_router.patch(
    "/activate-account/{token}/",
    response_model=dict,
    dependencies=[Depends(get_session)],
)
async def activate_account(
    token: str, session: Annotated[AsyncSession, Depends(get_session)]
):
    service = UserService(session=session)
    return await service.activate_account(token)


@user_service_router.get(
    "/get-user-by-id/{pk}/",
    response_model=SUser,
    dependencies=[Depends(get_session), Depends(get_redis)],
)
async def get_user_by_id(
    pk: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[StrictRedis, Depends(get_redis)],
):
    service = UserService(session=session, redis=redis)
    return await service.get_user_by_id(pk)


@user_service_router.get(
    "/get-user-by-username-password/{username}/{password}/",
    response_model=SUser,
    dependencies=[Depends(get_session)],
)
async def get_user_by_username_password(
    username: str, password: str, session: Annotated[AsyncSession, Depends(get_session)]
):
    service = UserService(session=session)
    return await service.get_user_by_username_password(username, password)


@user_service_router.put(
    "/update-user/",
    response_model=SUpdateUserResponse,
    dependencies=[Depends(get_redis), Depends(get_session), Depends(get_current_user)],
)
async def update_user(
    request: SUpdateUserRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[SUser, Depends(get_current_user)],
    redis: Annotated[StrictRedis, Depends(get_redis)],
):
    service = UserService(session=session, current_user=current_user, redis=redis)
    return await service.update_user(request)


@user_service_router.patch(
    "/close-account/",
    response_model=dict,
    dependencies=[Depends(get_session), Depends(get_redis), Depends(get_current_user)],
)
async def close_account(
    current_user: Annotated[SUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[StrictRedis, Depends(get_redis)],
):
    service = UserService(session=session, redis=redis, current_user=current_user)
    return await service.close_account()


@user_service_router.put(
    "/update-password/",
    response_model=SUpdatePasswordResponse,
    dependencies=[Depends(get_current_user), Depends(get_session)],
)
async def update_password(
    request: SUpdatePasswordRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[SUser, Depends(get_current_user)],
):
    service = UserService(session=session, current_user=current_user)
    return await service.update_password(request)


@user_service_router.post(
    "/password-reset/{email}", response_model=dict, dependencies=[Depends(get_session)]
)
async def password_reset(
    email: str, session: Annotated[AsyncSession, Depends(get_session)]
):
    service = UserService(session=session)
    return await service.password_reset(email)


@user_service_router.patch(
    "/password-reset-confirum/{token}/",
    response_model=dict,
    dependencies=[Depends(get_session)],
)
async def password_reset_confirum(
    token: str,
    request: SResetPasswordRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    service = UserService(session=session)
    return await service.password_reset_confirum(token, request)


@user_service_router.get(
    "/get-user-by-username/{username}/",
    response_model=SUser,
    dependencies=[Depends(get_redis), Depends(get_session)],
)
async def get_user_by_username(
    username: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[StrictRedis, Depends(get_redis)],
):
    service = UserService(session=session, redis=redis)
    return await service.get_user_by_username(username)
