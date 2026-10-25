def authenticate(username: str, password: str) -> bool:
    """Accept a non-empty username and password for this example."""
    return bool(username and password)
