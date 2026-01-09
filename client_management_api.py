"""
Client Management API
FastAPI endpoints for client creation and management.
"""
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict
import logging
import os

from client_manager import (
    create_client_config,
    update_client_system_prompt,
    get_client_config_from_mongodb,
    list_all_clients_from_mongodb
)

# Import LOCAL auth module (in same directory)
from auth.middleware import require_auth, check_client_ownership
from auth.models import User

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Client Management API",
    description="API for managing multi-tenant client configurations",
    version="1.0.0"
)

# Add CORS middleware (configurable via environment)
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Client-ID", "X-Request-ID"],  # Expose custom headers
    max_age=600,  # Cache preflight requests for 10 minutes
)

# Tenant Context Middleware
from fastapi import Request

@app.middleware("http")
async def tenant_context_middleware(request: Request, call_next):
    """
    Middleware to extract and store tenant/client context in request state.
    Logs which tenant is accessing which resource for monitoring and debugging.
    """
    # Extract client_id from query params or headers
    client_id = request.query_params.get("client_id") or request.headers.get("X-Client-ID")
    
    # Store in request state for easy access throughout request lifecycle
    request.state.client_id = client_id
    request.state.has_client_context = bool(client_id)
    
    # Log tenant context (optional - can be disabled in production)
    if client_id:
        logger.debug(f"[Tenant: {client_id}] {request.method} {request.url.path}")
    
    # Process request
    response = await call_next(request)
    
    # Add client_id to response headers for tracking
    if client_id:
        response.headers["X-Client-ID"] = client_id
    
    return response


class CreateClientRequest(BaseModel):
    client_id: str
    client_name: str
    owner_id: str
    system_prompt: Optional[str] = None
    languages: Optional[List[str]] = None
    mongodb_database_name: Optional[str] = None
    s3_bucket_name: Optional[str] = None
    s3_region: Optional[str] = None
    openai_api_key: Optional[str] = None
    tools: Optional[List[Dict]] = None
    additional_config: Optional[Dict] = None


class UpdateSystemPromptRequest(BaseModel):
    system_prompt: str


class GoogleTokenRequest(BaseModel):
    """Request model for Google token exchange"""
    google_token: str


class JWTTokenResponse(BaseModel):
    """Response model for JWT token"""
    access_token: str
    token_type: str
    expires_in: int
    user: Dict


@app.post("/auth/exchange", response_model=JWTTokenResponse)
async def exchange_google_token(request: GoogleTokenRequest):
    """
    Exchange Google ID token for JWT access token.
    
    Flow:
    1. Frontend sends Google ID token from NextAuth.js
    2. Backend validates Google token
    3. Backend generates JWT token
    4. Frontend uses JWT for subsequent API calls
    
    Args:
        request: Google token from NextAuth.js
        
    Returns:
        JWT access token and user info
    """
    from auth.google_validator import validate_google_token
    from auth.jwt_handler import create_jwt_token, get_token_expiration_time
    
    logger.info("Token exchange request received")
    
    # Validate Google token
    user_info = validate_google_token(request.google_token)
    
    if not user_info:
        logger.warning("Invalid Google token")
        raise HTTPException(
            status_code=401,
            detail="Invalid Google token"
        )
    
    logger.info(f"Google token validated for: {user_info['email']}")
    
    # Generate JWT token
    jwt_token = create_jwt_token(user_info)
    
    logger.info(f"JWT token generated for user: {user_info['email']}")
    
    return {
        "access_token": jwt_token,
        "token_type": "bearer",
        "expires_in": get_token_expiration_time(),
        "user": user_info
    }


@app.post("/clients")
async def create_client(
    request: CreateClientRequest,
    user: User = Depends(require_auth)
):
    """
    Create a new client configuration.
    Automatically creates S3 bucket and stores config in MongoDB.
    
    **Requires:** JWT authentication
    **Owner:** The authenticated user becomes the owner
    """
    try:
        # Use authenticated user's ID as owner_id
        result = create_client_config(
            client_id=request.client_id,
            client_name=request.client_name,
            owner_id=user.user_id,  # Use authenticated user's ID
            system_prompt=request.system_prompt,
            languages=request.languages,
            mongodb_database_name=request.mongodb_database_name,
            s3_bucket_name=request.s3_bucket_name,
            s3_region=request.s3_region,
            openai_api_key=request.openai_api_key,
            tools=request.tools,
            additional_config=request.additional_config
        )
        
        if result["status"] == "error":
            raise HTTPException(status_code=400, detail=result["message"])
        
        if result["status"] == "exists":
            raise HTTPException(status_code=409, detail=result["message"])
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating client: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.get("/clients")
async def list_clients():
    """List all clients"""
    try:
        clients = list_all_clients_from_mongodb()
        return {
            "status": "success",
            "count": len(clients),
            "clients": clients
        }
    except Exception as e:
        logger.error(f"Error listing clients: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.get("/clients/{id}")
async def get_client(id: str):
    """Get client configuration by MongoDB ObjectId"""
    try:
        config = get_client_config_from_mongodb(id)
        if not config:
            raise HTTPException(status_code=404, detail=f"Client with id {id} not found")
        
        return {
            "status": "success",
            "id": id,
            "config": config
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting client: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.put("/clients/{id}/system-prompt")
async def update_system_prompt(
    id: str,
    request: UpdateSystemPromptRequest,
    user: User = Depends(require_auth)
):
    """
    Update system prompt for a client by ObjectId.
    
    **Requires:** JWT authentication + ownership of the client
    """
    # Verify user owns this client
    check_client_ownership(id, user)
    
    try:
        result = update_client_system_prompt(id, request.system_prompt)
        
        if result["status"] == "error":
            raise HTTPException(status_code=400, detail=result["message"])
        
        if result["status"] == "not_found":
            raise HTTPException(status_code=404, detail=result["message"])
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating system prompt: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.post("/clients/{id}/system-prompt")
async def set_system_prompt(
    id: str,
    request: UpdateSystemPromptRequest,
    user: User = Depends(require_auth)
):
    """
    Set system prompt for a client by ObjectId (alias for PUT).
    
    **Requires:** JWT authentication + ownership of the client
    """
    return await update_system_prompt(id, request, user)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)
