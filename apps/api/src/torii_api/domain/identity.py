"""SPEC-0001 B2a1 identity values, not evidence of JWT/OIDC verification."""

from dataclasses import dataclass, field

from torii_api.domain.errors import DomainError


def _display_control(character: str) -> bool:
    codepoint = ord(character)
    return (
        codepoint < 0x20
        or 0x7F <= codepoint <= 0x9F
        or 0xD800 <= codepoint <= 0xDFFF
        or codepoint in {0x061C, 0x200E, 0x200F}
        or 0x202A <= codepoint <= 0x202E
        or 0x2066 <= codepoint <= 0x2069
    )


def normalize_display_name(name: object, preferred_username: object) -> str:
    """Clean a descriptive label, without using it as an identity identifier."""
    for candidate in (name, preferred_username):
        if type(candidate) is str:
            cleaned = "".join(char for char in candidate if not _display_control(char))
            normalized = cleaned.strip()[:200].rstrip()
            if normalized:
                return normalized
    return "Użytkownik"


@dataclass(frozen=True, slots=True)
class Identity:
    """Internal DTO; a future trusted verifier must establish its provenance."""

    issuer: str = field(repr=False)
    subject: str = field(repr=False)
    display_name: str = field(repr=False)

    def __post_init__(self) -> None:
        if (
            type(self.issuer) is not str
            or not 1 <= len(self.issuer) <= 2048
            or any(char == "\x00" or 0xD800 <= ord(char) <= 0xDFFF for char in self.issuer)
            or type(self.subject) is not str
            or not 1 <= len(self.subject) <= 255
            or any(not 0x21 <= ord(char) <= 0x7E for char in self.subject)
            or type(self.display_name) is not str
            or not 1 <= len(self.display_name) <= 200
            or normalize_display_name(self.display_name, None) != self.display_name
        ):
            raise DomainError(401, "unauthorized")
