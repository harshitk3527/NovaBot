import asyncio
import getpass
from uuid import uuid4

from sqlalchemy import select

from app.core.security import hash_password
from app.db.models import User, UserRole
from app.db.session import AsyncSessionLocal


async def main() -> None:
    email = input("Admin email: ").strip().lower()
    password = getpass.getpass("Admin password: ")
    async with AsyncSessionLocal() as db:
        existing = await db.scalar(select(User).where(User.email == email))
        if existing is not None:
            raise SystemExit("A user with that email already exists.")
        db.add(
            User(
                email=email,
                password_hash=hash_password(password),
                role=UserRole.ADMIN,
                tenant_id=uuid4(),
            )
        )
        await db.commit()
    print("Admin user created.")


if __name__ == "__main__":
    asyncio.run(main())
