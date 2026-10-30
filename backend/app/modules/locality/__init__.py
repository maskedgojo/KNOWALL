"""Module 4: Locality Intelligence & Community Discovery."""
from .common import locality_bp
from . import content, corrections, directory  # noqa: F401  (register routes on locality_bp)

__all__ = ["locality_bp"]
