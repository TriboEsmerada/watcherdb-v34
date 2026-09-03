"""
Authentication API Router
Handles user authentication and token management
"""

from datetime import timedelta
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from watcherdb.core.auth import (
    authenticate_user,
    create_access_token,
    get_current_active_user,
    require_admin,
    create_user,
    change_password,
    User,
    UserRole,
    Token,
    ACCESS_TOKEN_EXPIRE_MINUTES
)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


# ==========================================
# Models
# ==========================================
class UserCreate(BaseModel):
    """User creation request"""
    username: str
    password: str
    email: str
    full_name: str
    role: UserRole = UserRole.VIEWER


class PasswordChange(BaseModel):
    """Password change request"""
    current_password: str
    new_password: str


# ==========================================
# Endpoints
# ==========================================
@router.post("/token", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Authenticate user and return access token

    **Parameters:**
    - **username**: User's username
    - **password**: User's password

    **Returns:**
    - Access token (JWT) for subsequent API calls
    """
    user = authenticate_user(form_data.username, form_data.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role.value},
        expires_delta=access_token_expires
    )

    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=User)
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    """
    Get current user information

    **Returns:**
    - Current authenticated user details
    """
    return current_user


@router.post("/users", response_model=User, dependencies=[Depends(require_admin)])
async def create_new_user(user_data: UserCreate):
    """
    Create new user (Admin only)

    **Parameters:**
    - **username**: Unique username
    - **password**: User password
    - **email**: User email
    - **full_name**: User's full name
    - **role**: User role (admin, viewer)

    **Returns:**
    - Created user information
    """
    try:
        new_user = create_user(
            username=user_data.username,
            password=user_data.password,
            email=user_data.email,
            full_name=user_data.full_name,
            role=user_data.role
        )
        return User(**new_user.dict(exclude={"hashed_password"}))

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error creating user: {str(e)}"
        )


@router.post("/change-password")
async def change_user_password(
    password_data: PasswordChange,
    current_user: User = Depends(get_current_active_user)
):
    """
    Change current user's password

    **Parameters:**
    - **current_password**: Current password
    - **new_password**: New password

    **Returns:**
    - Success message
    """
    # Verify current password
    user = authenticate_user(current_user.username, password_data.current_password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect"
        )

    # Change password
    success = change_password(current_user.username, password_data.new_password)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error changing password"
        )

    return {"message": "Password changed successfully"}
