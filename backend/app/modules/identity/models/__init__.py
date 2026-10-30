"""Import all Phase 2A/2B/2C models before Flask-Migrate inspects metadata."""
from .user import User, AccountStatus
from .residence import SocietyProfile, Tower, Flat, Household
from .membership import Membership, ResidentCategory, MembershipStatus
from .invitation import Invitation
from .application import MembershipApplication, ApplicationStatus
from .document import VerificationDocument, DocumentType
from .ocr import OCRResult, OCRStatus
from .review import ApplicationReview, ReviewDecision
from .role import RoleAssignment, PermissionRole
from .auth_token import AuthToken, AuthTokenPurpose
from .audit import AuditLog
from .member_evidence import MemberEvidenceRequest, MemberEvidenceStatus

__all__ = [
    "User", "AccountStatus", "SocietyProfile", "Tower", "Flat", "Household",
    "Membership", "ResidentCategory", "MembershipStatus", "Invitation",
    "MembershipApplication", "ApplicationStatus", "VerificationDocument", "DocumentType",
    "OCRResult", "OCRStatus", "MemberEvidenceRequest", "MemberEvidenceStatus", "ApplicationReview", "ReviewDecision",
    "RoleAssignment", "PermissionRole", "AuthToken", "AuthTokenPurpose", "AuditLog",
]
