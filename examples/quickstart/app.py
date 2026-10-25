from auth import authenticate


def login(username: str, password: str) -> bool:
    """Example login handler backed by the local authentication module."""
    return authenticate(username, password)
