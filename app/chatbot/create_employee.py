"""Create or reset a TallyV employee portal account."""

import argparse
from getpass import getpass

from app.crud.catalog import find_user
from app.db.session import SessionLocal
from app.models import User
from app.services.security import hash_password


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("username")
    args = parser.parse_args()
    username = args.username.strip()
    if not 1 <= len(username) <= 80:
        parser.error("Tên tài khoản phải có từ 1 đến 80 ký tự.")
    password = getpass("Mật khẩu: ")
    if not 12 <= len(password) <= 200 or password != getpass("Nhập lại mật khẩu: "):
        parser.error("Mật khẩu phải trùng khớp và có từ 12 đến 200 ký tự.")
    with SessionLocal() as db:
        user = find_user(db, username)
        if user is not None and user.role != "EMPLOYEE":
            parser.error("Tên tài khoản đã được dùng bởi vai trò khác.")
        if user is None:
            user = User(username=username, role="EMPLOYEE", password_hash=hash_password(password))
            db.add(user)
        else:
            user.password_hash = hash_password(password)
        db.commit()
    print(f"Tài khoản tra cứu đã sẵn sàng: {username}")


if __name__ == "__main__":
    main()
