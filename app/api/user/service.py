from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from .models import User, Log
from typing import List, Optional

class UserService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_user(self, name: str, email: str, password: str) -> User:
        user = User(name=name, email=email, password=password)
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def get_users(self) -> List[User]:
        result = await self.session.execute(select(User))
        return result.scalars().all()

    async def update_user(self, user_id: int, name: str, email: str, password: Optional[str] = None) -> Optional[User]:
        result = await self.session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalars().first()
        if not user:
            return None
        user.name = name
        user.email = email
        if password is not None:
            user.password = password
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def delete_user(self, user_id: int) -> bool:
        result = await self.session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalars().first()
        if not user:
            return False
        await self.session.delete(user)
        await self.session.commit()
        return True

class LogService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_log(self, user_id: int, action: str) -> Log:
        log = Log(user_id=user_id, action=action)
        self.session.add(log)
        await self.session.commit()
        await self.session.refresh(log)
        return log

    async def get_logs(self, user_id: Optional[int] = None) -> List[Log]:
        query = select(Log)
        if user_id is not None:
            query = query.where(Log.user_id == user_id)
        result = await self.session.execute(query)
        return result.scalars().all()