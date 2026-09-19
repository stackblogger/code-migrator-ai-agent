"""Remove secrets from text before it leaves the machine."""

import re

REDACTED = "[REDACTED]"
PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),  # OpenAI style keys
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),  # AWS access key id
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),  # GitHub tokens
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),  # JWTs
    re.compile(r"(?i)\b(postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis)://[^\s:@/]+:[^\s@/]+@"),
]
# password = "x", SECRET_KEY: 'x', "apiKey": "x" -> keep the name, hide the value
ASSIGNMENT = re.compile(
    r"(?i)((?:password|passwd|secret|api[_-]?key|access[_-]?token|private[_-]?key)"
    r"[\"']?\s*[:=]\s*[\"'])([^\"']{4,})([\"'])"
)


def redact(text: str) -> tuple[str, int]:
    """Returns the cleaned text and how many secrets were hidden."""
    count = 0
    for pattern in PATTERNS:
        text, found = pattern.subn(REDACTED, text)
        count += found
    text, found = ASSIGNMENT.subn(lambda m: m.group(1) + REDACTED + m.group(3), text)
    return text, count + found
