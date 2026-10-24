"""Resident onboarding module: application/invitation HTTP APIs."""
from .routes import onboarding_bp, invitations_bp

__all__ = ["onboarding_bp", "invitations_bp"]
