"""Shared Module 2 lookups that do not encode unresolved governance policy."""

from .features import FEATURES, unimplemented_features
from .scope import SINGLETON_SOCIETY_ID, configured_society

__all__ = [
    "FEATURES",
    "SINGLETON_SOCIETY_ID",
    "configured_society",
    "unimplemented_features",
]
