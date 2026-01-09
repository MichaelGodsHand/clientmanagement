"""
Google OAuth Token Validator
Validates Google ID tokens from NextAuth.js
"""
import os
from typing import Optional, Dict
from google.oauth2 import id_token
from google.auth.transport import requests
from dotenv import load_dotenv

load_dotenv()

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")


def validate_google_token(token: str) -> Optional[Dict]:
    """
    Validate Google ID token and return user info.
    
    Args:
        token: Google ID token from NextAuth.js
        
    Returns:
        Dict with user info if valid, None if invalid
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
        
        # Token is valid, extract user info
        user_info = {
            "google_id": idinfo.get("sub"),
            "email": idinfo.get("email"),
            "name": idinfo.get("name"),
            "picture": idinfo.get("picture"),
            "email_verified": idinfo.get("email_verified", False)
        }
        
        return user_info
        
    except ValueError as e:
        # Invalid token
        print(f"❌ Invalid Google token: {e}")
        return None
    except Exception as e:
        # Other errors
        print(f"❌ Error validating Google token: {e}")
        return None
