import os
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.models.user import User
from app.services.gmail_service import GmailService
from app.db.database import get_db

router = APIRouter(prefix="/auth/google", tags=["auth"])
gmail_service = GmailService()

REDIRECT_URI = "http://localhost:8000/api/v1/auth/google/callback"

@router.get("/login")
async def google_login(
    current_user: User = Depends(get_current_user)
):
    """
    Starts the Google OAuth flow.
    Encodes the current user's ID into the state parameter 
    to associate the token on callback.
    """
    flow = gmail_service.get_flow(REDIRECT_URI)
    
    # Generate the authorization URL
    # state is used to pass user context (user_id) back from the callback
    auth_url, _ = flow.authorization_url(
        access_type="offline", 
        include_granted_scopes="true",
        state=str(current_user.id) 
    )
    
    return RedirectResponse(auth_url)

@router.get("/callback")
async def google_callback(
    code: str = Query(...),
    state: str = Query(...), # our user_id
    db: Session = Depends(get_db)
):
    """
    Callback for Google OAuth.
    Exchanges code for token and saves it for the user.
    """
    try:
        user_id = int(state)
        # Verify user exists in DB
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User context from state not found.")

        # Complete the flow
        flow = gmail_service.get_flow(REDIRECT_URI)
        flow.fetch_token(code=code)
        
        # Save token
        gmail_service.save_user_token(user_id, flow.credentials)
        
        # We can also update the user's oauth_provider in the DB
        user.oauth_provider = "google"
        db.commit()

        # Final success message or redirect to frontend
        # For now, we'll return a JSON or success page.
        # Ideally: RedirectResponse("http://localhost:5173/home?connected=true")
        return {"status": "success", "message": f"Gmail successfully connected for user {user_id}. You can now fetch your emails."}

    except Exception as e:
        print(f"Error in Google OAuth callback: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to complete OAuth flow: {str(e)}"
        )
