import os
import json
import logging
from typing import Optional
import firebase_admin
from firebase_admin import credentials, messaging

logger = logging.getLogger(__name__)

# Firebase App Initialization status
_firebase_initialized = False

def _initialize_firebase() -> bool:
    global _firebase_initialized
    if _firebase_initialized:
        return True

    # 1. Check if firebase-admin is already initialized elsewhere
    if firebase_admin._apps:
        _firebase_initialized = True
        return True

    # 2. Check for credentials in:
    #    a. Environment variable FIREBASE_CREDENTIALS (can be json string or file path)
    #    b. File 'firebase-credentials.json' in the project root directory
    cred_env = os.environ.get("FIREBASE_CREDENTIALS")
    cred_file_path = os.path.join(os.getcwd(), "firebase-credentials.json")
    
    cred = None

    try:
        if cred_env:
            if cred_env.strip().startswith("{"):
                # Raw JSON string configuration
                cred_dict = json.loads(cred_env)
                cred = credentials.Certificate(cred_dict)
                logger.info("Initializing Firebase using raw JSON environment credentials.")
            else:
                # Path configuration
                cred = credentials.Certificate(cred_env)
                logger.info(f"Initializing Firebase using credentials file from environment path: {cred_env}")
        elif os.path.exists(cred_file_path):
            cred = credentials.Certificate(cred_file_path)
            logger.info(f"Initializing Firebase using local key: {cred_file_path}")
            
        if cred:
            firebase_admin.initialize_app(cred)
            _firebase_initialized = True
            logger.info("🔥 Firebase Admin SDK initialized successfully!")
            return True
    except Exception as e:
        logger.error(f"Failed to initialize Firebase Admin SDK with credentials: {e}")

    # Graceful fallback explaining how to get real credentials
    logger.warning(
        "\n"
        "=======================================================================\n"
        "⚠️  [FIREBASE NOTIFICATIONS NOT SET UP / RUNNING IN DEV LOG MODE]\n"
        "-----------------------------------------------------------------------\n"
        "Sistem tidak mendeteksi kredensial Firebase Service Account.\n"
        "Notifikasi akan dicetak di log konsol backend untuk memudahkan pengujian.\n"
        "\n"
        "Untuk menggunakan Data Firebase Asli (Best Practice):\n"
        "1. Buka Firebase Console -> Project Settings -> Service Accounts.\n"
        "2. Klik 'Generate New Private Key' untuk mengunduh file JSON kredensial.\n"
        "3. Simpan file tersebut di project backend Anda dengan nama:\n"
        "   '%s'\n"
        "   (Atau set environment variable FIREBASE_CREDENTIALS dengan path file tersebut)\n"
        "=======================================================================\n",
        cred_file_path
    )
    return False

class FCMService:
    @staticmethod
    async def send_push_notification(token: str, title: str, body: str, data: Optional[dict] = None) -> bool:
        """
        Sends a push notification via Firebase Cloud Messaging.
        If a Firebase service account JSON is supplied, performs a real push.
        Otherwise, logs the push payload gracefully (mock mode) to facilitate immediate developer tests.
        """
        if not token:
            logger.warning("FCM token is empty, cannot send push notification.")
            return False

        # Attempt to initialize Firebase Admin
        is_initialized = _initialize_firebase()

        if is_initialized:
            try:
                # Real FCM push transmission using Firebase Admin SDK
                # Convert all keys/values in custom data dictionary to strings as required by Firebase
                fcm_data = {str(k): str(v) for k, v in (data or {}).items()}
                
                message = messaging.Message(
                    notification=messaging.Notification(
                        title=title,
                        body=body
                    ),
                    data=fcm_data,
                    token=token
                )
                
                # Send the message synchronously inside an executor block if necessary,
                # but standard messaging.send is fast enough for async contexts
                response = messaging.send(message)
                logger.info(f"Successfully sent Firebase push notification. Response ID: {response}")
                return True
            except Exception as e:
                logger.error(f"Error sending real Firebase notification: {e}")
                # Fall back to logging console payload in case of transmission failures
        
        # Consistent graceful console fallback log
        logger.info(
            f"\n=======================================================================\n"
            f"🔔 [FCM PUSH SEND EVENT]\n"
            f"Target Token: {token}\n"
            f"Title: {title}\n"
            f"Body: {body}\n"
            f"Data: {data}\n"
            f"=======================================================================\n"
        )
        return True
