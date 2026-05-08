"""Keyring-backed credential storage for UCLASS LMS."""
from typing import Optional

import keyring

SERVICE = "uclass-lms"
USERNAME_KEY = "_username_"  # marker entry storing the active username


def save_credentials(username: str, password: str) -> None:
    keyring.set_password(SERVICE, USERNAME_KEY, username)
    keyring.set_password(SERVICE, username, password)


def load_credentials() -> Optional[tuple[str, str]]:
    username = keyring.get_password(SERVICE, USERNAME_KEY)
    if not username:
        return None
    password = keyring.get_password(SERVICE, username)
    if not password:
        return None
    return username, password


def delete_credentials() -> None:
    username = keyring.get_password(SERVICE, USERNAME_KEY)
    if username:
        try:
            keyring.delete_password(SERVICE, username)
        except keyring.errors.PasswordDeleteError:
            pass
    try:
        keyring.delete_password(SERVICE, USERNAME_KEY)
    except keyring.errors.PasswordDeleteError:
        pass
