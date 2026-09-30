import re
from dataclasses import dataclass


@dataclass
class RedactionResult:
    clean_text: str
    redacted_items_count: int
    detected_entities: list[str]


class EnterprisePIIRedactor:
    """Masks SSNs, credit cards, emails, phone numbers, and cloud secrets."""

    PATTERNS = {
        "SSN": r"\b\d{3}-\d{2}-\d{4}\b",
        "CREDIT_CARD": r"\b(?:\d{4}[- ]?){3}\d{4}\b",
        "API_KEY": r"\b(?:sk-[a-zA-Z0-9]{32,}|AKIA[0-9A-Z]{16})\b",
        "EMAIL": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b",
        "PHONE": r"\b(?:\+?1[-.]?)?\(?[2-9]\d{2}\)?[-.]?\d{3}[-.]?\d{4}\b",
    }

    @classmethod
    def redact(cls, text: str) -> RedactionResult:
        clean = text
        detected = []
        count = 0

        for name, pattern in cls.PATTERNS.items():
            matches = re.findall(pattern, clean, flags=re.IGNORECASE)
            if matches:
                count += len(matches)
                detected.append(name)
                clean = re.sub(pattern, f"<REDACTED_{name}>", clean, flags=re.IGNORECASE)

        return RedactionResult(
            clean_text=clean,
            redacted_items_count=count,
            detected_entities=detected,
        )
