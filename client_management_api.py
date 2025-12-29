"""
Client Management API
FastAPI endpoints for client creation and management.
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict
import logging

from client_manager import (
    create_client_config,
    update_client_system_prompt,
    get_client_config_from_mongodb,
    list_all_clients_from_mongodb
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Client Management API",
    description="API for managing multi-tenant client configurations",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateClientRequest(BaseModel):
    client_id: str
    client_name: str
    owner_id: str
    system_prompt: Optional[str] = None
    mongodb_database_name: Optional[str] = None
    s3_bucket_name: Optional[str] = None
    s3_region: Optional[str] = None
    openai_api_key: Optional[str] = None
    tools: Optional[List[Dict]] = None
    additional_config: Optional[Dict] = None


class UpdateSystemPromptRequest(BaseModel):
    system_prompt: str


@app.post("/clients")
async def create_client(request: CreateClientRequest):
    """
    Create a new client configuration.
    Automatically creates S3 bucket and stores config in MongoDB.
    """
    try:
        result = create_client_config(
            client_id=request.client_id,
            client_name=request.client_name,
            owner_id=request.owner_id,
            system_prompt=request.system_prompt,
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


@app.get("/clients/{client_id}")
async def get_client(client_id: str):
    """Get client configuration"""
    try:
        config = get_client_config_from_mongodb(client_id)
        if not config:
            raise HTTPException(status_code=404, detail=f"Client {client_id} not found")
        
        return {
            "status": "success",
            "client_id": client_id,
            "config": config
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting client: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.put("/clients/{client_id}/system-prompt")
async def update_system_prompt(client_id: str, request: UpdateSystemPromptRequest):
    """
    Update system prompt for a client.
    """
    try:
        result = update_client_system_prompt(client_id, request.system_prompt)
        
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


@app.post("/clients/{client_id}/system-prompt")
async def set_system_prompt(client_id: str, request: UpdateSystemPromptRequest):
    """
    Set system prompt for a client (alias for PUT).
    """
    return await update_system_prompt(client_id, request)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)

