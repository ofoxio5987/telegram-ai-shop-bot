def verify_password(plain_password: str, stored_password: str) -> bool:
    if not stored_password:
        return False
    return plain_password.strip() == stored_password.strip()