"""
JWT Token Handler
Generates JWT tokens for API authentication
"""
import os
from datetime import datetime, timedelta
from typing import Dict
from jose import jwt
from dotenv import load_dotenv

load_dotenv()

# JWT Configuration (must match jwt_validator.py)
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-key-change-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRATION_MINUTES = int(os.getenv("JWT_EXPIRATION_MINUTES", "1440"))  # 24 hours


def create_jwt_token(user_info: Dict) -> str:
    """
    Create a JWT token from user information.
    
    Args:
        user_info: Dictionary containing user information (google_id, email, name, picture)
        
    Returns:
        Encoded JWT token string
    """
    # Create expiration time
    expire = datetime.utcnow() + timedelta(minutes=JWT_EXPIRATION_MINUTES)
    
    # Create payload
    payload = {
        "sub": user_info.get("google_id"),  # Subject (user ID)
        "email": user_info.get("email"),
        "name": user_info.get("name"),
        "picture": user_info.get("picture"),
        "exp": expire,
        "iat": datetime.utcnow(),  # Issued at
        "type": "access_token"
    }
    
    # Encode JWT
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    
    return token


def get_token_expiration_time() -> int:
    """Get token expiration time in seconds"""
    return JWT_EXPIRATION_MINUTES * 60
