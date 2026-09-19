"""Stable error codes, never user-controlled error messages."""


class DomainError(Exception):
    def __init__(self, status: int, code: str, pointers: tuple[str, ...] = ()) -> None:
        super().__init__(code)
        self.status = status
        self.code = code
        self.pointers = pointers
