"""
Client Management Service
Handles automatic client creation, S3 bucket creation, and MongoDB storage.
"""
import os
import json
import boto3
import uuid
from typing import Dict, Optional
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from botocore.exceptions import ClientError
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# MongoDB connection
MONGODB_URI = os.getenv("MONGODB_URI", "")
ADMIN_DB_NAME = os.getenv("ADMIN_DB_NAME", "widget")

# AWS S3 configuration
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")


def get_mongodb_client():
    """Get MongoDB client connection"""
    if not MONGODB_URI:
        logger.error("MONGODB_URI not configured")
        return None
    
    try:
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
        return client
    except (ConnectionFailure, ServerSelectionTimeoutError) as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        return None
    except Exception as e:
        logger.error(f"Error connecting to MongoDB: {e}")
        return None


def get_s3_client():
    """Get S3 client"""
    if not AWS_ACCESS_KEY_ID or not AWS_SECRET_ACCESS_KEY:
        logger.error("AWS credentials not configured")
        return None
    
    try:
        return boto3.client(
            's3',
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=AWS_REGION
        )
    except Exception as e:
        logger.error(f"Error creating S3 client: {e}")
        return None


def create_s3_bucket(bucket_name: str, region: str = None) -> Dict[str, any]:
    """
    Create an S3 bucket for a client.
    
    Args:
        bucket_name: Name of the bucket to create
        region: AWS region (defaults to configured region)
        
    Returns:
        Dict with status and bucket information
    """
    s3_client = get_s3_client()
    if not s3_client:
        return {
            "status": "error",
            "message": "S3 client not available",
            "bucket_name": bucket_name
        }
    
    region = region or AWS_REGION
    
    try:
        # Check if bucket already exists
        try:
            s3_client.head_bucket(Bucket=bucket_name)
            logger.info(f"Bucket {bucket_name} already exists")
            return {
                "status": "exists",
                "message": f"Bucket {bucket_name} already exists",
                "bucket_name": bucket_name,
                "region": region
            }
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            if error_code != '404':
                raise
        
        # Create bucket
        if region == 'us-east-1':
            # us-east-1 doesn't support LocationConstraint
            s3_client.create_bucket(Bucket=bucket_name)
        else:
            s3_client.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={'LocationConstraint': region}
            )
        
        # Disable "Block all public access" settings
        try:
            s3_client.put_public_access_block(
                Bucket=bucket_name,
                PublicAccessBlockConfiguration={
                    'BlockPublicAcls': False,
                    'IgnorePublicAcls': False,
                    'BlockPublicPolicy': False,
                    'RestrictPublicBuckets': False
                }
            )
            logger.info(f"Disabled block public access for {bucket_name}")
        except Exception as e:
            logger.warning(f"Could not disable block public access for {bucket_name}: {e}")
        
        # Apply bucket policy for public read access
        try:
            bucket_policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "PublicReadGetObject",
                        "Effect": "Allow",
                        "Principal": "*",
                        "Action": "s3:GetObject",
                        "Resource": f"arn:aws:s3:::{bucket_name}/*"
                    }
                ]
            }
            s3_client.put_bucket_policy(
                Bucket=bucket_name,
                Policy=json.dumps(bucket_policy)
            )
            logger.info(f"Applied public read bucket policy for {bucket_name}")
        except Exception as e:
            logger.warning(f"Could not apply bucket policy for {bucket_name}: {e}")
        
        # Enable versioning (optional but recommended)
        try:
            s3_client.put_bucket_versioning(
                Bucket=bucket_name,
                VersioningConfiguration={'Status': 'Enabled'}
            )
        except Exception as e:
            logger.warning(f"Could not enable versioning for {bucket_name}: {e}")
        
        logger.info(f"Successfully created S3 bucket: {bucket_name} in region {region}")
        return {
            "status": "created",
            "message": f"Bucket {bucket_name} created successfully",
            "bucket_name": bucket_name,
            "region": region
        }
        
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', '')
        error_message = e.response.get('Error', {}).get('Message', str(e))
        
        if error_code == 'BucketAlreadyOwnedByYou':
            logger.info(f"Bucket {bucket_name} already owned by you")
            return {
                "status": "exists",
                "message": f"Bucket {bucket_name} already owned by you",
                "bucket_name": bucket_name,
                "region": region
            }
        
        logger.error(f"Error creating S3 bucket {bucket_name}: {error_code} - {error_message}")
        return {
            "status": "error",
            "message": f"Failed to create bucket: {error_message}",
            "bucket_name": bucket_name,
            "error_code": error_code
        }
    except Exception as e:
        logger.error(f"Unexpected error creating S3 bucket {bucket_name}: {e}")
        return {
            "status": "error",
            "message": f"Unexpected error: {str(e)}",
            "bucket_name": bucket_name
        }


def create_client_config(
    client_id: str,
    client_name: str,
    owner_id: str,
    system_prompt: Optional[str] = None,
    mongodb_database_name: Optional[str] = None,
    s3_bucket_name: Optional[str] = None,
    s3_region: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    tools: Optional[list] = None,
    additional_config: Optional[dict] = None
) -> Dict[str, any]:
    """
    Create a new client configuration and store in MongoDB.
    Automatically creates S3 bucket if needed.
    
    Args:
        client_id: Unique client identifier
        client_name: Display name for the client
        owner_id: Owner identifier for the client
        system_prompt: System prompt for the agent (optional)
        mongodb_database_name: MongoDB database name (defaults to client_id.upper())
        s3_bucket_name: S3 bucket name (ignored - always generated as {client_id}-{uuid})
        s3_region: AWS region for S3 bucket (defaults to configured region)
        openai_api_key: OpenAI API key for this client (optional)
        tools: List of tools configuration (optional)
        additional_config: Additional configuration options (optional)
        
    Returns:
        Dict with status and created configuration
    """
    # Validate required fields
    if not client_id or not client_name or not owner_id:
        return {
            "status": "error",
            "message": "client_id, client_name, and owner_id are required"
        }
    
    # Normalize client_id (lowercase, no spaces)
    client_id = client_id.lower().strip().replace(' ', '-')
    
    # Get MongoDB client
    mongo_client = get_mongodb_client()
    if not mongo_client:
        return {
            "status": "error",
            "message": "MongoDB connection failed"
        }
    
    try:
        admin_db = mongo_client[ADMIN_DB_NAME]
        clients_collection = admin_db["client_configs"]
        
        # Check if client already exists
        existing = clients_collection.find_one({"client_id": client_id})
        if existing:
            return {
                "status": "exists",
                "message": f"Client {client_id} already exists",
                "client_id": client_id,
                "config": existing
            }
        
        # Set defaults
        mongodb_database_name = mongodb_database_name or client_id.upper()
        # Always generate UUID and append to client_id for bucket name
        bucket_uuid = str(uuid.uuid4())
        s3_bucket_name = f"{client_id}-{bucket_uuid}"
        s3_region = s3_region or AWS_REGION
        
        # Create S3 bucket
        bucket_result = create_s3_bucket(s3_bucket_name, s3_region)
        if bucket_result["status"] == "error":
            logger.warning(f"Could not create S3 bucket for {client_id}: {bucket_result['message']}")
            # Continue anyway - bucket might be created manually later
        
        # Build configuration document
        config = {
            "client_id": client_id,
            "client_name": client_name,
            "owner_id": owner_id,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "mongodb": {
                "database_name": mongodb_database_name
            },
            "s3": {
                "bucket_name": s3_bucket_name,
                "region": s3_region
            },
            "agent": {
                "system_prompt": system_prompt or "",
                "llm_config": {
                    "model": os.getenv("LLM_MODEL", "gemini-live-2.5-flash-preview-native-audio-09-2025"),
                    "temperature": float(os.getenv("LLM_TEMPERATURE", "0.1"))
                },
                "tools": tools or []
            },
            "preprocessor": {
                "url": os.getenv("PREPROCESSOR_URL", "http://localhost:8080")
            },
            "postprocessor": {
                "url": os.getenv("POSTPROCESSOR_URL", "http://localhost:8003")
            }
        }
        
        # Add OpenAI API key if provided
        if openai_api_key:
            config["openai"] = {
                "api_key": openai_api_key
            }
        
        # Merge additional config
        if additional_config:
            config.update(additional_config)
        
        # Insert into MongoDB
        result = clients_collection.insert_one(config)
        
        logger.info(f"Created client configuration for {client_id} (MongoDB ID: {result.inserted_id})")
        
        # Remove MongoDB _id from response
        config.pop('_id', None)
        
        return {
            "status": "created",
            "message": f"Client {client_id} created successfully",
            "client_id": client_id,
            "config": config,
            "s3_bucket": bucket_result
        }
        
    except Exception as e:
        logger.error(f"Error creating client configuration: {e}", exc_info=True)
        return {
            "status": "error",
            "message": f"Failed to create client: {str(e)}"
        }


def update_client_system_prompt(client_id: str, system_prompt: str) -> Dict[str, any]:
    """
    Update system prompt for a client.
    
    Args:
        client_id: Unique client identifier
        system_prompt: New system prompt text
        
    Returns:
        Dict with status and updated configuration
    """
    mongo_client = get_mongodb_client()
    if not mongo_client:
        return {
            "status": "error",
            "message": "MongoDB connection failed"
        }
    
    try:
        admin_db = mongo_client[ADMIN_DB_NAME]
        clients_collection = admin_db["client_configs"]
        
        # Update system prompt
        result = clients_collection.update_one(
            {"client_id": client_id},
            {
                "$set": {
                    "agent.system_prompt": system_prompt,
                    "updated_at": datetime.utcnow().isoformat()
                }
            }
        )
        
        if result.matched_count == 0:
            return {
                "status": "not_found",
                "message": f"Client {client_id} not found"
            }
        
        # Get updated config
        updated_config = clients_collection.find_one({"client_id": client_id})
        if updated_config:
            updated_config.pop('_id', None)
        
        logger.info(f"Updated system prompt for client {client_id}")
        
        return {
            "status": "updated",
            "message": f"System prompt updated for client {client_id}",
            "client_id": client_id,
            "config": updated_config
        }
        
    except Exception as e:
        logger.error(f"Error updating system prompt: {e}", exc_info=True)
        return {
            "status": "error",
            "message": f"Failed to update system prompt: {str(e)}"
        }


def get_client_config_from_mongodb(client_id: str) -> Optional[Dict]:
    """
    Get client configuration from MongoDB.
    
    Args:
        client_id: Unique client identifier
        
    Returns:
        Client configuration dict or None if not found
    """
    mongo_client = get_mongodb_client()
    if not mongo_client:
        return None
    
    try:
        admin_db = mongo_client[ADMIN_DB_NAME]
        clients_collection = admin_db["client_configs"]
        
        config = clients_collection.find_one({"client_id": client_id})
        if config:
            config.pop('_id', None)
        
        return config
        
    except Exception as e:
        logger.error(f"Error getting client config from MongoDB: {e}", exc_info=True)
        return None


def list_all_clients_from_mongodb() -> list:
    """
    List all clients from MongoDB.
    
    Returns:
        List of client configurations
    """
    mongo_client = get_mongodb_client()
    if not mongo_client:
        return []
    
    try:
        admin_db = mongo_client[ADMIN_DB_NAME]
        clients_collection = admin_db["client_configs"]
        
        clients = list(clients_collection.find({}, {"_id": 0}))
        return clients
        
    except Exception as e:
        logger.error(f"Error listing clients from MongoDB: {e}", exc_info=True)
        return []

