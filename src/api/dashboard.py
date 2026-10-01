"""HTML Dashboard loader for Aegis Enterprise AI Platform."""

from pathlib import Path

_TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "index.html"


def get_dashboard_html() -> str:
    """Returns the full HTML and client-side JavaScript for the platform landing page."""
    return _TEMPLATE_PATH.read_text(encoding="utf-8")
