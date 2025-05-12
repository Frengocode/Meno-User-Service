from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from dto.dto import UserDTO
from services.user.models import User
from services.user.scheme import (
    SCreateUserRequest,
    SUser,
    SCreateUserResponse,
    SUpdateUserRequest,
    SUpdateUserResponse,
    SUpdatePasswordRequest,
    SUpdatePasswordResponse,
    SResetPasswordRequest,
)
from utils.utils import send_email, bcrypt, verify
from redis.asyncio import StrictRedis
from typing import Optional
import uuid
import json


class UserService:
    def __init__(
        self,
        session: AsyncSession,
        current_user: Optional[SUser] = None,
        redis: Optional[StrictRedis] = None,
    ):
        self.session = session
        self.redis = redis
        self.current_user = current_user

    async def create_user(self, request: SCreateUserRequest) -> SCreateUserResponse:
        user_dto = UserDTO(session=self.session, model=User)
        exist_user = await user_dto.get(username=request.username)
        if exist_user:
            raise HTTPException(
                detail="This Username all ready used by other user", status_code=404
            )

        if len(request.password) < 8:
            raise HTTPException(detail="Password is short", status_code=400)

        hashed_password = bcrypt(request.password)
        request.password = hashed_password

        user = await user_dto.create(request)
        await send_email(
            "Activate account",
            body=f"Activate Your account http://localhost:8000/user-service/api/v1/activate-account/{user.token}/",
            to_email=user.email,
        )

        return SCreateUserResponse(**user.__dict__)

    async def activate_account(self, token: str):
        user_dto = UserDTO(session=self.session, model=User)
        user = await user_dto.get(token=token)
        if not user:
            raise HTTPException(detail="User not found", status_code=404)

        user.token = uuid.uuid4()
        user.is_active = True
        await self.session.commit()
        return {"detail": "Account Succesfully activeted"}

    async def get_user_by_id(
        self,
        pk: int,
    ):
        cached_data = await self.redis.get(f"get-user-by-id-{pk}")
        if cached_data:
            return SUser(**json.loads(cached_data))

        user_dto = UserDTO(session=self.session, model=User)
        user = await user_dto.get(id=pk)
        if not user:
            raise HTTPException(detail="User not Found", status_code=400)

        response = SUser(**user.__dict__)

        await self.redis.setex(f"get-user-by-id-{pk}", 500, json.dumps(response.dict()))

        return response

    async def get_user_by_username_password(self, username: str, password: str):
        user_dto = UserDTO(session=self.session, model=User)
        user = await user_dto.get(username=username)
        if not user:
            raise HTTPException(detail="User not found", status_code=404)

        if not verify(password, user.password):
            raise HTTPException(detail="Incorrect password", status_code=400)

        return SUser(**user.__dict__)

    async def get_user_by_username(self, username: str):
        cached_data = await self.redis.get(f"get-user-by-username-{username}")
        if cached_data:
            return SUser(**json.loads(cached_data))

        user_dto = UserDTO(session=self.session, model=User)
        user = await user_dto.get(username=username)
        if not user:
            raise HTTPException(detail="User Not Found", status_code=404)
        response = SUser(**user.__dict__)
        await self.redis.setex(
            f"get-user-by-username-{username}", 500, json.dumps(cached_data)
        )
        return response

    async def update_user(self, request: SUpdateUserRequest):
        user_dto = UserDTO(session=self.session, model=User)
        exsit_user_email = await user_dto.get(email=request.email)
        if exsit_user_email:
            raise HTTPException(
                detail="Email all ready used by other user",
                status_code=400,
            )

        exits_user_username = await user_dto.get(username=request.username)
        if exits_user_username:
            raise HTTPException(
                detail="Username all ready used by other user", status_code=400
            )

        update = await user_dto.update(request, id=self.current_user.id)
        await self.redis.delete(f"get-user-by-id-{self.current_user.id}")
        await self.redis.save()
        return SUpdateUserResponse(**update.__dict__)

    async def close_account(self):
        user_dto = UserDTO(session=self.session, model=User)
        user = await user_dto.get(id=self.current_user.id)
        if not user:
            raise HTTPException(detail="User not found", status_code=404)

        if user.is_closed:
            user.is_closed = False
            await self.session.commit()
            await self.redis.delete(f"get-user-by-id-{self.current_user.id}")
            await self.redis.save()
            return {"detail": "Account succsessfully Unclosed"}

        user.is_closed = True
        await self.session.commit()
        await self.redis.delete(f"get-user-by-id-{self.current_user.id}")
        await self.redis.save()
        return {"detail": "Account Succsesfully Closed"}

    async def update_password(self, request: SUpdatePasswordRequest):
        user_dto = UserDTO(session=self.session, model=User)

        user = await user_dto.get(id=self.current_user.id)

        if len(request.new_password) < 8:
            raise HTTPException(detail="Password is short", status_code=404)
        if not verify(request.old_password, user.password):
            raise HTTPException(detail="In correct password", status_code=400)

        user.password = bcrypt(request.new_password)

        await self.session.commit()
        await self.session.refresh(user)
        return SUpdatePasswordResponse(
            id=self.current_user.id,
            new_password=request.new_password,
        )

    async def password_reset(self, email: str):
        user_dto = UserDTO(session=self.session, model=User)
        user = await user_dto.get(email=email)
        if not user:
            raise HTTPException(detail="User not found", status_code=404)

        await send_email(
            subject="Password Reset",
            body=f"http://localhost:8000/user-service/api/v1/password-reset-confirum/{user.token}/, this link for reset password",
            to_email=email,
        )

        return {"detail": "Token sended succsesfully"}

    async def password_reset_confirum(self, token: str, request: SResetPasswordRequest):
        user_dto = UserDTO(session=self.session, model=User)
        user = await user_dto.get(token=token)
        if not user:
            raise HTTPException(detail="User not found", status_code=404)

        if request.password1 != request.password2:
            raise HTTPException(detail="Passwords didint mathing", status_code=404)

        user.password = bcrypt(request.password2)
        user.token = uuid.uuid4()
        await self.session.commit()
        await self.session.refresh(user)
        return {"detail": "Password reset succsessfully"}
