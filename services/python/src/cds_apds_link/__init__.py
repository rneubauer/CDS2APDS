"""Reference link service for the CDS-APDS Link Profile v0.1."""

from .app import create_app
from .config import Settings

__all__ = ["create_app", "Settings"]
__version__ = "0.1.0"
