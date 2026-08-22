import logging

from fastapi import APIRouter, Depends
from sqlalchemy import func as _func
from sqlalchemy.orm import Session

from app.core.auth import get_current_active_user
from app.db.database import get_db
from app.models.email import Email
from app.models.processing_state import ProcessingState
from app.models.user import User
from app.schemas.processing_state import ProcessingStateResponse

router = APIRouter(tags=["processing-state"])
logger = logging.getLogger(__name__)

_VALID_CATEGORIES = {"rdv", "action", "attente", "bonsplans", "info"}


def _get_or_create_state(db: Session, user_id: int) -> ProcessingState:
    state = db.query(ProcessingState).filter(ProcessingState.user_id == user_id).first()
    if not state:
        state = ProcessingState(user_id=user_id, is_active=False)
        db.add(state)
        db.commit()
        db.refresh(state)
    return state


def _compute_counts(db: Session, user_id: int) -> tuple[int, int, dict[str, dict[str, int]]]:
    """Compute total/processed/per-category counts from the Email table (not stored,
    to avoid counter drift — see ProcessingState docstring)."""
    total_emails = db.query(_func.count(Email.id)).filter(Email.user_id == user_id).scalar() or 0
    processed_emails = (
        db.query(_func.count(Email.id))
        .filter(Email.user_id == user_id, Email.category.isnot(None))
        .scalar()
        or 0
    )

    rows = (
        db.query(Email.category, Email.is_done, _func.count(Email.id))
        .filter(Email.user_id == user_id)
        .group_by(Email.category, Email.is_done)
        .all()
    )
    processed_by_category: dict[str, dict[str, int]] = {
        cat: {"total": 0, "done": 0} for cat in _VALID_CATEGORIES
    }
    for cat, is_done, n in rows:
        key = cat if cat in _VALID_CATEGORIES else "info"
        processed_by_category[key]["total"] += n
        if is_done:
            processed_by_category[key]["done"] += n

    return total_emails, processed_emails, processed_by_category


def _build_response(db: Session, state: ProcessingState) -> ProcessingStateResponse:
    total_emails, processed_emails, processed_by_category = _compute_counts(db, state.user_id)
    return ProcessingStateResponse(
        user_id=state.user_id,
        is_active=state.is_active,
        total_emails=total_emails,
        processed_emails=processed_emails,
        processed_by_category=processed_by_category,
        updated_at=state.updated_at,
    )


@router.get("/processing-state", response_model=ProcessingStateResponse)
def get_state(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ProcessingStateResponse:
    """Return the current user's processing state, with counts computed live
    from the Email table."""
    state = _get_or_create_state(db, current_user.id)
    return _build_response(db, state)


@router.post("/processing-state/toggle", response_model=ProcessingStateResponse)
def toggle_state(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ProcessingStateResponse:
    """Flip is_active for the current user and return the fresh computed state."""
    state = _get_or_create_state(db, current_user.id)
    state.is_active = not state.is_active
    db.commit()
    db.refresh(state)
    return _build_response(db, state)
