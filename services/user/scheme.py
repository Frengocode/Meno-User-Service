from pydantic import BaseModel, EmailStr
from typing import Optional


class SUser(BaseModel):
    id: int
    username: str
    email: EmailStr
    picture_url: Optional[str] = None
    is_closed: bool
    is_active: bool


class SCreateUserRequest(BaseModel):
    username: str
    email: str
    password: str


class SCreateUserResponse(SCreateUserRequest):
    id: int


class SUpdateUserRequest(BaseModel):
    username: str
    name: Optional[str] = None
    email: EmailStr


class SUpdateUserResponse(SUpdateUserRequest):
    id: int


class SUpdatePasswordRequest(BaseModel):
    new_password: str
    old_password: str


class SUpdatePasswordResponse(SUpdatePasswordRequest):
    id: int
    old_password: Optional[str] = None


class SResetPasswordRequest(BaseModel):
    password1: str
    password2: str
