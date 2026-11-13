import asyncio
import argparse
import getpass
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.security import hash_password
from app.db.models import User, UserRole
from app.db.session import AsyncSessionLocal


async def main(email: str, password: str) -> None:
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
    parser = argparse.ArgumentParser(description="Create the first admin user.")
    parser.add_argument("--email", help="Admin email address")
    parser.add_argument("--password", help="Admin password; omit to be prompted securely")
    args = parser.parse_args()
    email = (args.email or input("Admin email: ")).strip().lower()
    password = args.password or getpass.getpass("Admin password: ")
    asyncio.run(main(email, password))
