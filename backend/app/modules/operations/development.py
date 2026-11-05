"""Society development projects with milestones. Only a Society Admin edits them."""
from flask import Blueprint
from flask_login import current_user
from sqlalchemy import select

from app.extensions import db
from app.modules.identity.auth.routes import error, json_object
from app.modules.identity.models.user import utc_now

from .common import (
    audit, choice, day, integer, iso, manage_operations, no_store, pagination, resident_read, schema_missing,
    society_or_error, text,
)
from .models import DevelopmentProject, PhotoSubject, ProjectMilestone, ProjectStatus
from .photos import photos_for

development_bp = Blueprint("operations_development", __name__)


def _milestones(project_ids) -> dict:
    if not project_ids:
        return {}
    rows = db.session.scalars(
        select(ProjectMilestone).where(ProjectMilestone.project_id.in_(project_ids))
        .order_by(ProjectMilestone.due_date.asc(), ProjectMilestone.created_at.asc())
    ).all()
    photos = photos_for(PhotoSubject.PROJECT_MILESTONE, [row.id for row in rows])
    grouped: dict = {}
    for row in rows:
        grouped.setdefault(row.project_id, []).append({
            "id": str(row.id), "title": row.title, "due_date": iso(row.due_date), "status": row.status.value,
            "percent": row.percent, "progress_note": row.progress_note, "updated_at": iso(row.updated_at),
            "photos": photos.get(row.id, []),
        })
    return grouped


def _projects_payload(rows) -> list[dict]:
    milestones = _milestones([row.id for row in rows])
    payload = []
    for row in rows:
        items = milestones.get(row.id, [])
        payload.append({
            "id": str(row.id),
            "title": row.title,
            "description": row.description,
            "status": row.status.value,
            "budget_note": row.budget_note,
            "expected_completion": iso(row.expected_completion),
            "progress_percent": round(sum(item["percent"] for item in items) / len(items)) if items else 0,
            "milestones": items,
            "updated_at": iso(row.updated_at),
        })
    return payload


def _project(project_id, society_id, *, lock=False):
    query = select(DevelopmentProject).where(
        DevelopmentProject.id == project_id, DevelopmentProject.society_id == society_id,
    )
    if lock:
        query = query.with_for_update()
    return db.session.scalar(query)


@development_bp.get("/api/development")
@resident_read
def list_projects():
    return _list()


@development_bp.get("/api/admin/development")
@manage_operations
def admin_list_projects():
    return _list()


def _list():
    missing = schema_missing()
    if missing:
        return missing
    society, failure = society_or_error()
    if failure:
        return failure
    page = pagination()
    if page is None:
        return error("VALIDATION_ERROR", "Invalid limit or offset.", 400)
    limit, offset = page
    rows = db.session.scalars(
        select(DevelopmentProject).where(DevelopmentProject.society_id == society.id)
        .order_by(DevelopmentProject.updated_at.desc(), DevelopmentProject.id.desc()).limit(limit).offset(offset)
    ).all()
    return no_store({"projects": _projects_payload(rows), "pagination": {"limit": limit, "offset": offset}})


@development_bp.get("/api/development/<uuid:project_id>")
@resident_read
def get_project(project_id):
    missing = schema_missing()
    if missing:
        return missing
    society, failure = society_or_error()
    if failure:
        return failure
    project = _project(project_id, society.id)
    if project is None:
        return error("PROJECT_NOT_FOUND", "Project not found.", 404)
    return no_store({"project": _projects_payload([project])[0]})


@development_bp.post("/api/development")
@manage_operations
def create_project():
    missing = schema_missing()
    if missing:
        return missing
    body, failure = json_object({"title", "description", "budget_note", "expected_completion"})
    if failure:
        return failure
    society, failure = society_or_error()
    if failure:
        return failure
    problems: dict = {}
    title = text(body.get("title"), "title", 3, 160, problems)
    description = text(body.get("description"), "description", 1, 8000, problems)
    budget_note = text(body.get("budget_note"), "budget_note", 1, 300, problems, required=False)
    expected = day(body.get("expected_completion"), "expected_completion", problems)
    if problems:
        return error("VALIDATION_ERROR", "Check the project and try again.", 400, fields=problems)
    now = utc_now()
    project = DevelopmentProject(
        society_id=society.id, title=title, description=description, status=ProjectStatus.PLANNED,
        budget_note=budget_note, expected_completion=expected, created_by_user_id=current_user.id,
        created_at=now, updated_at=now,
    )
    db.session.add(project)
    db.session.flush()
    audit("PROJECT_CREATED", "DEVELOPMENT_PROJECT", project.id, {"title": title})
    db.session.commit()
    return no_store({"project": _projects_payload([project])[0]}, 201)


@development_bp.patch("/api/development/<uuid:project_id>")
@manage_operations
def update_project(project_id):
    missing = schema_missing()
    if missing:
        return missing
    body, failure = json_object({"status", "budget_note", "expected_completion"})
    if failure:
        return failure
    society, failure = society_or_error()
    if failure:
        return failure
    project = _project(project_id, society.id, lock=True)
    if project is None:
        return error("PROJECT_NOT_FOUND", "Project not found.", 404)
    problems: dict = {}
    if "status" in body:
        status = choice(body.get("status"), "status", ProjectStatus, problems)
        if status == ProjectStatus.COMPLETED and any(
            item["status"] != ProjectStatus.COMPLETED.value for item in _milestones([project.id]).get(project.id, [])
        ):
            problems["status"] = "Complete every milestone first."
        elif status:
            project.status = status
    if "budget_note" in body:
        project.budget_note = text(body.get("budget_note"), "budget_note", 1, 300, problems, required=False)
    if "expected_completion" in body:
        project.expected_completion = day(body.get("expected_completion"), "expected_completion", problems)
    if problems:
        db.session.rollback()
        return error("VALIDATION_ERROR", "Check the project and try again.", 400, fields=problems)
    project.updated_at = utc_now()
    audit("PROJECT_UPDATED", "DEVELOPMENT_PROJECT", project.id, {"fields": sorted(body), "status": project.status.value})
    db.session.commit()
    return no_store({"project": _projects_payload([project])[0]})


@development_bp.post("/api/development/<uuid:project_id>/milestones")
@manage_operations
def add_milestone(project_id):
    missing = schema_missing()
    if missing:
        return missing
    body, failure = json_object({"title", "due_date"})
    if failure:
        return failure
    society, failure = society_or_error()
    if failure:
        return failure
    project = _project(project_id, society.id, lock=True)
    if project is None:
        return error("PROJECT_NOT_FOUND", "Project not found.", 404)
    problems: dict = {}
    title = text(body.get("title"), "title", 3, 160, problems)
    due = day(body.get("due_date"), "due_date", problems)
    if problems:
        db.session.rollback()
        return error("VALIDATION_ERROR", "Check the milestone and try again.", 400, fields=problems)
    now = utc_now()
    db.session.add(ProjectMilestone(
        project_id=project.id, title=title, due_date=due, status=ProjectStatus.PLANNED, percent=0,
        updated_by_user_id=current_user.id, created_at=now, updated_at=now,
    ))
    if project.status == ProjectStatus.COMPLETED:
        project.status = ProjectStatus.IN_PROGRESS
    project.updated_at = now
    audit("PROJECT_MILESTONE_ADDED", "DEVELOPMENT_PROJECT", project.id, {"title": title})
    db.session.commit()
    return no_store({"project": _projects_payload([project])[0]}, 201)


@development_bp.patch("/api/development/<uuid:project_id>/milestones/<uuid:milestone_id>")
@manage_operations
def update_milestone(project_id, milestone_id):
    missing = schema_missing()
    if missing:
        return missing
    body, failure = json_object({"status", "percent", "progress_note"})
    if failure:
        return failure
    society, failure = society_or_error()
    if failure:
        return failure
    project = _project(project_id, society.id, lock=True)
    milestone = db.session.scalar(select(ProjectMilestone).where(
        ProjectMilestone.id == milestone_id, ProjectMilestone.project_id == project_id,
    )) if project else None
    if milestone is None:
        db.session.rollback()
        return error("MILESTONE_NOT_FOUND", "Milestone not found.", 404)
    problems: dict = {}
    if "status" in body:
        milestone.status = choice(body.get("status"), "status", ProjectStatus, problems) or milestone.status
    if "percent" in body:
        milestone.percent = integer(body.get("percent"), "percent", 0, 100, problems) or 0
    if "progress_note" in body:
        milestone.progress_note = text(body.get("progress_note"), "progress_note", 1, 4000, problems) or ""
    if milestone.status == ProjectStatus.COMPLETED:
        milestone.percent = 100
    if problems:
        db.session.rollback()
        return error("VALIDATION_ERROR", "Check the milestone and try again.", 400, fields=problems)
    now = utc_now()
    milestone.updated_by_user_id = current_user.id
    milestone.updated_at = now
    if project.status == ProjectStatus.PLANNED and milestone.status != ProjectStatus.PLANNED:
        project.status = ProjectStatus.IN_PROGRESS
    project.updated_at = now
    audit("PROJECT_MILESTONE_UPDATED", "DEVELOPMENT_PROJECT", project.id, {
        "milestone": milestone.title, "status": milestone.status.value, "percent": milestone.percent,
    })
    db.session.commit()
    return no_store({"project": _projects_payload([project])[0]})
