"""
Firebase Admin SDK Configuration
Initialize Firebase Admin SDK for push notifications
"""

import firebase_admin
from firebase_admin import credentials
import os

# Initialize Firebase Admin SDK
def initialize_firebase():
    """
    Initialize Firebase Admin SDK
    Place your serviceAccountKey.json in the root directory
    """
    try:
        # Check if already initialized
        if firebase_admin._apps:
            return True
        
        # Path to service account key
        # Option 1: Use environment variable (recommended for production)
        cred_path = os.getenv('FIREBASE_CREDENTIALS_PATH', 'serviceAccountKey.json')
        
        # Check if file exists
        if not os.path.exists(cred_path):
            return False
        
        # Initialize with service account
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        
        return True
        
    except Exception as e:
        return False


# Optional: Initialize on module import
# Uncomment if you want to initialize automatically
# initialize_firebase()
