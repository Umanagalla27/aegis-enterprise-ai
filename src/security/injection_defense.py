import re


class InjectionDefenseEngine:
    SIGNATURES = [
        r"ignore\s+(all\s+)?(previous|prior)\s+instructions?",
        r"system\s*:?\s*override",
        r"you\s+are\s+now\s+(a\s+)?(developer|admin|god\s+mode|unrestricted)",
        r"bypass\s+security\s+protocols?",
        r"reveal\s+(all\s+)?(api\s+keys?|passwords?|secrets?)",
        r"jailbreak",
        r"disregard\s+(the\s+above|(all\s+)?(previous|prior)\s+instructions?)",
    ]

    @classmethod
    def is_adversarial(cls, text: str) -> tuple[bool, str]:
        for sig in cls.SIGNATURES:
            if re.search(sig, text, flags=re.IGNORECASE):
                return True, f"Adversarial signature detected: '{sig}'"
        return False, "Clean input"
