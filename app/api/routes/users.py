from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_current_active_user
from app.core.config import settings
from app.core.encryption import encrypt
from app.core.security import create_access_token, hash_password, verify_password
from app.db.database import get_db
from app.models.user import User
from app.schemas.user import LoginRequest, Token, UserCreate, UserResponse, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])

@router.post("/", status_code=status.HTTP_201_CREATED, response_model=UserResponse)
def create_user(user_in: UserCreate, db: Session = Depends(get_db)):
    """Create a new user account."""
    existing_user = db.query(User).filter_by(email=user_in.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    user = User(
        email=user_in.email,
        password_hash=hash_password(user_in.password),
        role=user_in.role
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

@router.post("/login", response_model=Token)
def login(login_data: LoginRequest, db: Session = Depends(get_db)):
    """
    Authenticate user and return JWT access token.
    Token expires after ACCESS_TOKEN_EXPIRE_MINUTES (default: 60 minutes).
    """
    # Find user by email
    user = db.query(User).filter(User.email == login_data.email).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify password
    if not verify_password(login_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create access token
    access_token = create_access_token(
        subject=str(user.id),
        data={"email": user.email, "role": user.role},
        secret=settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )

    return Token(access_token=access_token, token_type="bearer")

@router.get("/me", response_model=UserResponse)
def get_current_user_info(current_user: User = Depends(get_current_active_user)):
    """Get the currently authenticated user's information."""
    return current_user

@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get a specific user by ID.
    Only accessible by authenticated users.
    """
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return user

@router.patch("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    user_update: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Update a user's information.
    Users can only update their own account unless they have admin role.
    """
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Check permissions: users can only update themselves unless admin
    if current_user.id != user_id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this user"
        )

    # Update fields that were provided
    update_data = user_update.model_dump(exclude_unset=True)

    # Check if email is being changed and if it's already taken
    if "email" in update_data and update_data["email"] != user.email:
        existing_user = db.query(User).filter(User.email == update_data["email"]).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

    # Hash password if it's being updated
    if "password" in update_data:
        update_data["password_hash"] = hash_password(update_data.pop("password"))

    # Apply updates
    for field, value in update_data.items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)
    return user

_VALID_PROVIDERS = {"google", "apple", "outlook"}


class CalendarSetupRequest(BaseModel):
    calendar_provider: str
    # "google", "apple", or "outlook"
    apple_caldav_user: str | None = None
    # Required when calendar_provider == "apple": the user's Apple ID email
    apple_caldav_password: str | None = None
    # Required when calendar_provider == "apple": App Password from appleid.apple.com
    # Sent in plain text over HTTPS; stored Fernet-encrypted in the DB.
    # For "outlook": complete the OAuth flow via GET /api/v1/auth/microsoft first.


@router.patch("/me/calendar-setup", response_model=UserResponse)
def setup_calendar(
    body: CalendarSetupRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Add a calendar provider to the user's active providers list.

    Each call APPENDS the provider — calling this twice with "google" then
    "apple" results in both being active. Use DELETE /me/calendar-disconnect
    to remove a provider.

    - google: no extra credentials needed (reuses Gmail OAuth token)
    - apple: requires apple_caldav_user + apple_caldav_password (App Password)
    - outlook: OAuth must be completed first via GET /api/v1/auth/microsoft
    """
    provider = body.calendar_provider
    if provider not in _VALID_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"calendar_provider must be one of: {', '.join(sorted(_VALID_PROVIDERS))}",
        )

    if provider == "apple":
        if not body.apple_caldav_user or not body.apple_caldav_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="apple_caldav_user and apple_caldav_password are required for Apple Calendar",
            )
        current_user.apple_caldav_user = body.apple_caldav_user
        current_user.apple_caldav_password = encrypt(body.apple_caldav_password)

    # Append to calendar_providers list (deduplicated)
    current_providers: list[str] = list(current_user.calendar_providers or [])
    if provider not in current_providers:
        current_providers.append(provider)
    current_user.calendar_providers = current_providers
    # Keep legacy field in sync for backwards compatibility
    current_user.calendar_provider = provider

    db.commit()
    db.refresh(current_user)
    return current_user


@router.delete("/me/calendar-disconnect", response_model=UserResponse)
def disconnect_calendar(
    provider: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Remove a calendar provider from the user's active providers list.
    Pass provider as a query parameter, e.g. ?provider=apple
    """
    current_providers: list[str] = list(current_user.calendar_providers or [])
    if provider not in current_providers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Provider '{provider}' is not currently connected",
        )
    current_providers.remove(provider)
    current_user.calendar_providers = current_providers
    if current_user.calendar_provider == provider:
        current_user.calendar_provider = current_providers[-1] if current_providers else None

    db.commit()
    db.refresh(current_user)
    return current_user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Delete a user account.
    Users can only delete their own account unless they have admin role.
    """
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Check permissions: users can only delete themselves unless admin
    if current_user.id != user_id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this user"
        )

    db.delete(user)
    db.commit()
    return None
