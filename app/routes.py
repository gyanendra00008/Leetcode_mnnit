import math
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, asc, case, or_
from config import settings
from app.database import get_db
from app.models import LeetCodeUser, AdminAuditLog
from app.schemas import (
    UserResponse,
    UserListResponse,
    CollectorStatus,
    CollectorActionResponse,
    AdminLoginRequest,
    AdminLoginResponse,
    AdminUserUpdateRequest,
    AdminUserUpdateResponse,
    AdminUserUpdateDetail,
    AdminDiscoverRequest,
    AdminAuditLogItem,
)
from app.auth import (
    verify_password,
    create_admin_session,
    destroy_admin_session,
    get_session_token_from_request,
    get_current_admin,
    get_optional_admin,
    log_audit_event,
)
from app.crawler import crawler

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# =====================================================================
# 1. ADMIN AUTHENTICATION ENDPOINTS
# =====================================================================

@router.post("/admin/login", response_model=AdminLoginResponse, tags=["Admin Auth"])
async def admin_login(
    payload: AdminLoginRequest,
    response: Response,
    db: Session = Depends(get_db)
):
    """
    Authenticate the administrator using configured credentials.
    Sets an HttpOnly, SameSite=Lax session cookie and returns a session token.
    """
    username = payload.username.strip()
    if username != settings.ADMIN_USERNAME or not verify_password(payload.password, settings.ADMIN_PASSWORD):
        log_audit_event("LOGIN_ATTEMPT", target=username, status="FAILED", details="Invalid admin credentials", admin_username=username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid administrator username or password."
        )

    token = create_admin_session(db, username)
    response.set_cookie(
        key="admin_session",
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=settings.SESSION_EXPIRE_HOURS * 3600
    )
    log_audit_event("LOGIN", target=username, status="SUCCESS", details="Admin authenticated successfully", admin_username=username)

    return AdminLoginResponse(
        status="success",
        message="Authentication successful.",
        token=token,
        username=username
    )


@router.post("/admin/logout", tags=["Admin Auth"])
@router.get("/admin/logout", tags=["Admin Auth"])
async def admin_logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """Log out admin, invalidate session token, and clear session cookie."""
    token = get_session_token_from_request(request)
    if token:
        destroy_admin_session(db, token)
        log_audit_event("LOGOUT", status="SUCCESS", details="Admin session terminated")

    response.delete_cookie("admin_session")

    # If requested by browser navigation, redirect to login
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_302_FOUND)

    return {"status": "success", "message": "Logged out successfully."}


# =====================================================================
# 2. ADMIN-ONLY PROTECTED OPERATIONS (Mutations contacting LeetCode)
# =====================================================================

@router.post("/admin/update-user", response_model=AdminUserUpdateResponse, tags=["Admin Operations"])
async def admin_update_user(
    payload: AdminUserUpdateRequest,
    current_admin: str = Depends(get_current_admin)
):
    """
    Admin-Only: Fetch latest statistics for a specific user from LeetCode.
    If user is not in database, adds them.
    If user exists, updates their record without creating duplicates.
    """
    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username is required.")

    res = await crawler.update_user(username)
    if not res.get("success"):
        err = res.get("error", "Failed to fetch user stats")
        log_audit_event("UPDATE_USER", target=username, status="FAILED", details=err, admin_username=current_admin)
        raise HTTPException(
            status_code=res.get("status_code", status.HTTP_400_BAD_REQUEST),
            detail=f"Failed to fetch profile for '{username}': {err}"
        )

    is_new = res.get("is_new", False)
    msg = "User added successfully." if is_new else "User updated successfully."
    log_audit_event("UPDATE_USER", target=username, status="SUCCESS", details=f"{msg} Rating: {res.get('rating_display')}, Solved: {res.get('total_questions')}", admin_username=current_admin)

    return AdminUserUpdateResponse(
        status="success",
        message=msg,
        is_new=is_new,
        user=AdminUserUpdateDetail(
            username=res.get("username", username),
            actual_name=res.get("actual_name") or "N/A",
            rating=res.get("rating"),
            rating_display=res.get("rating_display", "N/A"),
            unrated_reason=res.get("unrated_reason"),
            total_questions=res.get("total_questions", 0),
            easy_questions=res.get("easy_questions", 0),
            medium_questions=res.get("medium_questions", 0),
            hard_questions=res.get("hard_questions", 0),
            college_relevance=res.get("college_relevance", "unknown"),
            last_updated=res.get("last_updated")
        )
    )


@router.post("/admin/update-all", response_model=CollectorActionResponse, tags=["Admin Operations"])
async def admin_update_all(
    stale_days: Optional[int] = Query(None, description="Only update users older than N days"),
    current_admin: str = Depends(get_current_admin)
):
    """
    Admin-Only: Refresh statistics for all existing users from LeetCode.
    Protected against concurrent executions (returns HTTP 409 Conflict if active).
    """
    if crawler.is_running:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An operation is already running (Action: {crawler.current_action}). Please wait for it to complete or stop it."
        )

    refreshed = await crawler.update_all(stale_days=stale_days)
    if refreshed:
        msg = f"Statistics update started for users older than {stale_days} days." if stale_days else "Full statistics refresh started."
        log_audit_event("UPDATE_ALL", target=f"stale_days={stale_days}", status="SUCCESS", details=msg, admin_username=current_admin)
        return CollectorActionResponse(status="started", message=msg)
    else:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not start update: operation is already running."
        )


@router.post("/admin/discover", response_model=CollectorActionResponse, tags=["Admin Operations"])
async def admin_discover(
    payload: AdminDiscoverRequest = AdminDiscoverRequest(),
    current_admin: str = Depends(get_current_admin)
):
    """
    Admin-Only: Starts graph discovery crawler up to target users.
    Protected against concurrent executions (returns HTTP 409 Conflict if active).
    """
    if crawler.is_running:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An operation is already running (Action: {crawler.current_action}). Please wait for it to complete or stop it."
        )

    started = await crawler.start(target=payload.target)
    if started:
        log_audit_event("DISCOVER", target=f"target={payload.target}", status="SUCCESS", details=f"Target: {payload.target}", admin_username=current_admin)
        return CollectorActionResponse(status="started", message=f"Discovery started with target {payload.target} users.")
    else:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not start discovery: operation is already running."
        )


@router.post("/admin/stop", response_model=CollectorActionResponse, tags=["Admin Operations"])
async def admin_stop(
    current_admin: str = Depends(get_current_admin)
):
    """Admin-Only: Request the running crawler/updater to stop gracefully."""
    if not crawler.is_running:
        return CollectorActionResponse(status="idle", message="No active operation is running.")
    crawler.stop()
    log_audit_event("STOP", status="SUCCESS", details="Stop requested", admin_username=current_admin)
    return CollectorActionResponse(status="stopping", message="Operation stop requested.")


@router.get("/admin/audit-logs", response_model=List[AdminAuditLogItem], tags=["Admin Operations"])
async def admin_get_audit_logs(
    limit: int = Query(50, ge=1, le=200),
    current_admin: str = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Admin-Only: Fetch latest administrative audit events."""
    logs = db.query(AdminAuditLog).order_by(AdminAuditLog.id.desc()).limit(limit).all()
    return [AdminAuditLogItem(**l.to_dict()) for l in logs]


# =====================================================================
# 3. LEGACY COLLECTOR ENDPOINTS (Secured with Admin Auth)
# =====================================================================

@router.post("/collector/start", response_model=CollectorActionResponse, tags=["Legacy Protected"])
async def start_collector_legacy(
    current_admin: str = Depends(get_current_admin)
):
    """Legacy start endpoint - requires admin authentication."""
    if crawler.is_running:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Crawler is already active.")
    started = await crawler.start()
    if started:
        log_audit_event("START_LEGACY", status="SUCCESS", admin_username=current_admin)
        return CollectorActionResponse(status="started", message="Crawler started successfully.")
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Crawler is already active.")


@router.post("/collector/stop", response_model=CollectorActionResponse, tags=["Legacy Protected"])
async def stop_collector_legacy(
    current_admin: str = Depends(get_current_admin)
):
    """Legacy stop endpoint - requires admin authentication."""
    if not crawler.is_running:
        return CollectorActionResponse(status="idle", message="Collector is not running.")
    crawler.stop()
    log_audit_event("STOP_LEGACY", status="SUCCESS", admin_username=current_admin)
    return CollectorActionResponse(status="stopping", message="Collector stop requested.")


@router.post("/collector/update-all", response_model=CollectorActionResponse, tags=["Legacy Protected"])
@router.post("/collector/update", response_model=CollectorActionResponse, tags=["Legacy Protected"])
@router.post("/collector/refresh", response_model=CollectorActionResponse, tags=["Legacy Protected"])
async def update_all_users_legacy(
    stale_days: Optional[int] = Query(None, description="Only update users older than N days"),
    current_admin: str = Depends(get_current_admin)
):
    """Legacy update-all endpoint - requires admin authentication."""
    if crawler.is_running:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An operation is already running.")
    refreshed = await crawler.update_all(stale_days=stale_days)
    if refreshed:
        log_audit_event("UPDATE_ALL_LEGACY", status="SUCCESS", admin_username=current_admin)
        return CollectorActionResponse(status="started", message="Full statistics refresh started.")
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Could not start update.")


@router.post("/collector/update/{username}", response_model=CollectorActionResponse, tags=["Legacy Protected"])
async def update_single_user_legacy(
    username: str,
    current_admin: str = Depends(get_current_admin)
):
    """Legacy single user update endpoint - requires admin authentication."""
    res = await crawler.update_user(username)
    if res.get("success"):
        log_audit_event("UPDATE_USER_LEGACY", target=username, status="SUCCESS", admin_username=current_admin)
        return CollectorActionResponse(
            status="success",
            message=f"Successfully updated statistics for '{username}'."
        )
    else:
        log_audit_event("UPDATE_USER_LEGACY", target=username, status="FAILED", details=res.get("error"), admin_username=current_admin)
        raise HTTPException(
            status_code=res.get("status_code", status.HTTP_400_BAD_REQUEST),
            detail=f"Failed to update '{username}': {res.get('error')}"
        )


# =====================================================================
# 4. PUBLIC READ-ONLY ENDPOINTS (ZERO LeetCode API Calls)
# =====================================================================

@router.get("/collector/status", response_model=CollectorStatus, tags=["Public Data"])
async def get_collector_status():
    """Public read-only: Get current cached counts and live state (ZERO external calls)."""
    status_data = crawler.get_status()
    return CollectorStatus(**status_data)


@router.get("/users", response_model=UserListResponse, tags=["Public Data"])
async def get_users(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(5000, ge=1, le=10000, description="Users to fetch (default: 5000)"),
    sort: str = Query("rating", description="Sort field: rating, total_questions, easy_questions, medium_questions, hard_questions, username, name"),
    order: str = Query("desc", pattern="^(asc|desc)$", description="Sort order: asc or desc"),
    search: Optional[str] = Query(None, description="Filter by username or actual name search term"),
    mnnit: bool = Query(False, description="Filter for MNNIT-only verified users"),
    db: Session = Depends(get_db),
):
    """
    Public read-only: Paginated user list with sorting, name/username search, and MNNIT filter.
    Reads STRICTLY from local database/cache. ZERO LeetCode API requests.
    """
    query = db.query(LeetCodeUser)

    # Search filter (matches username OR actual_name)
    if search:
        search_term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                LeetCodeUser.username.ilike(search_term),
                LeetCodeUser.actual_name.ilike(search_term)
            )
        )

    # MNNIT filter
    if mnnit:
        query = query.filter(LeetCodeUser.college_relevance == "MNNIT")

    # Determine sort attribute
    sort_column_map = {
        "rating": LeetCodeUser.rating,
        "total_questions": LeetCodeUser.total_questions,
        "easy_questions": LeetCodeUser.easy_questions,
        "medium_questions": LeetCodeUser.medium_questions,
        "hard_questions": LeetCodeUser.hard_questions,
        "username": LeetCodeUser.username,
        "name": LeetCodeUser.actual_name,
        "created_at": LeetCodeUser.created_at,
        "updated_at": LeetCodeUser.updated_at,
    }

    sort_col = sort_column_map.get(sort, LeetCodeUser.rating)

    if order == "desc":
        if sort == "rating":
            # Put null ratings last when sorting by rating DESC
            query = query.order_by(
                case((LeetCodeUser.rating.is_(None), 1), else_=0),
                desc(sort_col)
            )
        else:
            query = query.order_by(desc(sort_col))
    else:
        if sort == "rating":
            # Put null ratings last when sorting by rating ASC
            query = query.order_by(
                case((LeetCodeUser.rating.is_(None), 1), else_=0),
                asc(sort_col)
            )
        else:
            query = query.order_by(asc(sort_col))

    total = query.count()
    pages = math.ceil(total / limit) if total > 0 else 1
    offset = (page - 1) * limit
    users = query.offset(offset).limit(limit).all()

    return UserListResponse(
        total=total,
        page=page,
        limit=limit,
        pages=pages,
        users=[UserResponse.model_validate(u) for u in users]
    )


# =====================================================================
# 5. HTML PAGE ROUTES
# =====================================================================

@router.get("/admin/login", response_class=HTMLResponse, tags=["Admin Pages"])
async def admin_login_page(request: Request, db: Session = Depends(get_db)):
    """Serve the admin login page. If already authenticated, redirect to /admin."""
    admin_user = get_optional_admin(request, db)
    if admin_user:
        return RedirectResponse(url="/admin", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(request=request, name="admin_login.html")


@router.get("/admin", response_class=HTMLResponse, tags=["Admin Pages"])
async def admin_dashboard_page(request: Request, db: Session = Depends(get_db)):
    """Serve the admin control dashboard. Requires active admin session."""
    admin_user = get_optional_admin(request, db)
    if not admin_user:
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={"admin_username": admin_user}
    )
