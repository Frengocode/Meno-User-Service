from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from sqlalchemy import select
from dataclasses import dataclass
from typing import Optional, Any


@dataclass
class BaseDTO:
    session: AsyncSession
    model: Any

    async def create(self, request):
        obj = self.model(**request.__dict__)
        self.session.add(obj)
        await self.session.commit()
        await self.session.refresh(obj)
        return obj

    async def get(self, **filters):
        return await self.filter(**filters)

    async def filter(self, **fitlers):
        stmt = select(self.model).filter_by(**fitlers)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def update(self, request, **filters):
        result = await self.get(**filters)
        if not result:
            raise HTTPException(detail="Obj not found", status_code=404)

        for name, value in request.dict().items():
            setattr(result, name, value)
        await self.session.commit()
        await self.session.refresh(result)
        return result
