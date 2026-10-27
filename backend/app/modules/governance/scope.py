"""Resolve the existing single-society profile.

This repeats the Notice V1 rule: the server uses society profile id 1 and
never accepts a society id from the client. It does not decide society
scoping, moderation, dispute privacy, polls, or voting for any other table.
Those choices remain pending in the Module 2 decision register.
"""
from app.extensions import db
from app.modules.identity.models import SocietyProfile

SINGLETON_SOCIETY_ID = 1


def configured_society() -> SocietyProfile | None:
    return db.session.get(SocietyProfile, SINGLETON_SOCIETY_ID)
