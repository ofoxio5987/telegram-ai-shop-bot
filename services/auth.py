import bcrypt


def verify_password(plain_password: str, stored_password: str) -> bool:
    if not stored_password:
        return False

    # Если в базе bcrypt-хэш
    if stored_password.startswith("$2a$") or stored_password.startswith("$2b$") or stored_password.startswith("$2y$"):
        try:
            return bcrypt.checkpw(plain_password.encode(), stored_password.encode())
        except Exception:
            return False

    # Если в базе обычный текст
    return plain_password == stored_password