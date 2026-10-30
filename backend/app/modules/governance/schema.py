"""Detect Module 2 tables that the development database does not have yet."""
from sqlalchemy import inspect

from app.extensions import db
from app.modules.identity.auth.routes import error

MIGRATION_HINT = (
    "This feature is unavailable until its database migration is applied. "
    "Existing notices and accounts were not changed."
)


def tables_present(*names: str) -> bool:
    existing = set(inspect(db.engine).get_table_names())
    return all(name in existing for name in names)


def schema_required(*names: str):
    if tables_present(*names):
        return None
    return error("SCHEMA_NOT_READY", MIGRATION_HINT, 503)
