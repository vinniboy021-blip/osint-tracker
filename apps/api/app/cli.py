import argparse
import getpass

from sqlalchemy import select

from app.auth import hash_password
from app.db import SessionLocal
from app.models import User


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd")
    a = sub.add_parser("create-admin")
    a.add_argument("--email", required=True)
    a.add_argument("--password")
    args = p.parse_args()
    if args.cmd == "create-admin":
        password = args.password or getpass.getpass("Senha do administrador: ")
        with SessionLocal() as db:
            user = db.scalar(select(User).where(User.email == args.email.lower()))
            if user:
                user.role = "admin"
                user.password_hash = hash_password(password)
                user.is_active = True
            else:
                db.add(User(email=args.email.lower(), password_hash=hash_password(password), role="admin"))
            db.commit()
            print("Administrador criado/atualizado")


if __name__ == "__main__":
    main()
