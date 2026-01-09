"""
Google OAuth Token Validator
Validates Google ID tokens from NextAuth.js
"""
import os
from typing import Optional, Dict
from google.oauth2 import id_token
from google.auth.transport import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
MONGODB_URI = os.getenv("MONGODB_URI", "")
ADMIN_DB_NAME = os.getenv("ADMIN_DB_NAME", "widget")


def get_mongodb_client():
    """Get MongoDB client"""
    if not MONGODB_URI:
        print("❌ MONGODB_URI not configured")
        return None
    
    try:
        return MongoClient(MONGODB_URI)
    except Exception as e:
        print(f"❌ Error connecting to MongoDB: {e}")
        return None


def validate_google_token(token: str) -> Optional[Dict]:
    """
    Validate Google ID token and return user info with MongoDB _id.
    
    Args:
        token: Google ID token from NextAuth.js
        
    Returns:
        Dict with user info including MongoDB _id if valid, None if invalid
    """
    if not GOOGLE_CLIENT_ID:
        print("❌ GOOGLE_CLIENT_ID not configured")
        return None
    
    try:
        # Verify the token
        idinfo = id_token.verify_oauth2_token(
            token, 
            requests.Request(), 
            GOOGLE_CLIENT_ID
        )
        
        # Extract Google ID
        google_id = idinfo.get("sub")
        email = idinfo.get("email")
        
        # Look up user in MongoDB by googleId to get their _id
        mongo_client = get_mongodb_client()
        if not mongo_client:
            print("❌ Cannot connect to MongoDB to look up user")
            return None
        
        try:
            admin_db = mongo_client[ADMIN_DB_NAME]
            users_collection = admin_db["users"]
            
            # Find user by googleId
            user_doc = users_collection.find_one({"googleId": google_id})
            
            if not user_doc:
                print(f"❌ User not found in MongoDB for googleId: {google_id}")
                return None
            
            # Return user info with MongoDB _id
            user_info = {
                "user_id": str(user_doc["_id"]),  # MongoDB ObjectId as string
                "google_id": google_id,
                "email": email,
                "name": idinfo.get("name"),
                "picture": idinfo.get("picture"),
                "email_verified": idinfo.get("email_verified", False)
            }
            
            return user_info
            
        finally:
            mongo_client.close()
        
    except ValueError as e:
        # Invalid token
        print(f"❌ Invalid Google token: {e}")
        return None
    except Exception as e:
        # Other errors
        print(f"❌ Error validating Google token: {e}")
        return None
