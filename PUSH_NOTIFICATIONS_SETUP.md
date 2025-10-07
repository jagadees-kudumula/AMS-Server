# Push Notifications Setup Guide for AMS Backend

## 📋 Overview
This guide will help you set up Firebase Cloud Messaging (FCM) for push notifications in the AMS application.

## 🔧 Backend Setup

### Step 1: Install Firebase Admin SDK

```bash
# Activate virtual environment
.\myenv\Scripts\Activate.ps1

# Install firebase-admin
pip install firebase-admin
```

Or install from requirements.txt:
```bash
pip install -r requirements.txt
```

### Step 2: Set Up Firebase Project

1. **Go to Firebase Console**
   - Visit: https://console.firebase.google.com/
   - Click "Add Project" or select existing project

2. **Add Android App**
   - Click "Add App" → Select Android icon
   - Package name: `com.amsrkv` (or your actual package name from React Native)
   - App nickname: `AMS Android App`
   - Click "Register App"
   - Download `google-services.json`
   - **For React Native**: Place in `android/app/google-services.json`

3. **Add iOS App (if needed)**
   - Click "Add App" → Select iOS icon
   - Bundle ID: Get from your Xcode project
   - Download `GoogleService-Info.plist`
   - **For React Native**: Place in `ios/AMSRKV/GoogleService-Info.plist`

### Step 3: Generate Service Account Key (Backend)

1. In Firebase Console → Click ⚙️ (Settings) → **Project Settings**
2. Go to **Service Accounts** tab
3. Click **Generate New Private Key**
4. Download the JSON file
5. **Rename** to `serviceAccountKey.json`
6. **Place** in your backend root directory:
   ```
   AMSRKV-B/
     ├── app/
     ├── myenv/
     ├── run.py
     ├── serviceAccountKey.json  ← HERE
     └── requirements.txt
   ```

⚠️ **IMPORTANT**: Add `serviceAccountKey.json` to `.gitignore` to avoid committing secrets!

```
# Add to .gitignore
serviceAccountKey.json
*.json
!google-services.json
```

### Step 4: Initialize Firebase in Your App

Update `app/__init__.py`:

```python
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from app.config import Config

db = SQLAlchemy()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    db.init_app(app)
    CORS(app)
    
    # Initialize Firebase Admin SDK
    from app.firebase_config import initialize_firebase
    initialize_firebase()
    
    from app.routes import routes
    app.register_blueprint(routes)
    
    return app
```

### Step 5: Update Database

Run these commands to create the new tables:

```bash
# Option 1: Using Flask-Migrate (recommended)
flask db migrate -m "Add FCM tokens and notification logs tables"
flask db upgrade

# Option 2: Using Python shell
python
>>> from app import create_app, db
>>> app = create_app()
>>> with app.app_context():
...     db.create_all()
>>> exit()
```

### Step 6: Test the Setup

```bash
# Start the server
python run.py
```

Check for this message in the console:
```
✅ Firebase Admin SDK initialized successfully
```

If you see:
```
⚠️ Firebase credentials file not found
```
Make sure `serviceAccountKey.json` is in the root directory.

## 📡 API Endpoints

### 1. Register FCM Token
**Endpoint**: `POST /api/notifications/register-token`

**Request**:
```json
{
  "email": "e230123@rguktrkv.ac.in",
  "fcm_token": "firebase_device_token_here",
  "device_type": "android"
}
```

**Response**:
```json
{
  "success": true,
  "message": "FCM token registered successfully"
}
```

### 2. Send Notification (CR Only)
**Endpoint**: `POST /api/cr/send-notification`

**Request**:
```json
{
  "cr_email": "cr@rguktrkv.ac.in",
  "title": "Class Update",
  "message": "Tomorrow's class venue changed to Lab 201"
}
```

**Response**:
```json
{
  "success": true,
  "message": "Notification sent to 43 students",
  "details": {
    "total_students": 45,
    "registered_devices": 43,
    "successful": 43,
    "failed": 0
  }
}
```

### 3. Get Notification History
**Endpoint**: `GET /api/notifications/history?cr_email=cr@rguktrkv.ac.in`

**Response**:
```json
{
  "success": true,
  "notifications": [
    {
      "id": 1,
      "title": "Class Update",
      "message": "Venue changed",
      "recipient_count": 43,
      "sent_at": "2025-10-07T10:30:00",
      "status": "success"
    }
  ]
}
```

## 🔒 Security Notes

1. **Never commit** `serviceAccountKey.json` to Git
2. **Use environment variables** in production:
   ```bash
   export FIREBASE_CREDENTIALS_PATH=/path/to/serviceAccountKey.json
   ```
3. **Validate CR status** before sending notifications (already implemented)
4. **Validate email domain** (@rguktrkv.ac.in only)

## 🧪 Testing Push Notifications

### Test 1: Register Token
```bash
curl -X POST http://localhost:5000/api/notifications/register-token \
  -H "Content-Type: application/json" \
  -d '{
    "email": "e230123@rguktrkv.ac.in",
    "fcm_token": "test_token_123",
    "device_type": "android"
  }'
```

### Test 2: Send Notification (requires CR status)
```bash
curl -X POST http://localhost:5000/api/cr/send-notification \
  -H "Content-Type: application/json" \
  -d '{
    "cr_email": "cr@rguktrkv.ac.in",
    "title": "Test Notification",
    "message": "This is a test message"
  }'
```

## 🐛 Troubleshooting

### Firebase not initialized
**Error**: `Firebase Admin SDK not installed`
**Solution**: `pip install firebase-admin`

### Service account key not found
**Error**: `Firebase credentials file not found`
**Solution**: Place `serviceAccountKey.json` in root directory

### Permission denied
**Error**: `Not authorized. Only CRs can send notifications`
**Solution**: Make sure the email belongs to a CR in the database

### No devices registered
**Error**: `No students with registered devices found`
**Solution**: Students need to install and login to the app first

## 📱 Frontend Integration

The React Native app should:

1. **Install dependencies**:
   ```bash
   npm install @react-native-firebase/app @react-native-firebase/messaging
   ```

2. **Request permission and get FCM token**:
   ```javascript
   import messaging from '@react-native-firebase/messaging';
   
   async function requestUserPermission() {
     const authStatus = await messaging().requestPermission();
     const enabled =
       authStatus === messaging.AuthorizationStatus.AUTHORIZED ||
       authStatus === messaging.AuthorizationStatus.PROVISIONAL;
   
     if (enabled) {
       const fcmToken = await messaging().getToken();
       // Send to backend
       await registerToken(userEmail, fcmToken);
     }
   }
   ```

3. **Call backend API**:
   ```javascript
   const registerToken = async (email, fcmToken) => {
     await fetch(`${API_BASE_URL}/api/notifications/register-token`, {
       method: 'POST',
       headers: { 'Content-Type': 'application/json' },
       body: JSON.stringify({
         email,
         fcm_token: fcmToken,
         device_type: Platform.OS
       })
     });
   };
   ```

## ✅ Checklist

- [ ] Firebase project created
- [ ] `google-services.json` added to React Native Android
- [ ] `GoogleService-Info.plist` added to React Native iOS (if applicable)
- [ ] `serviceAccountKey.json` downloaded and placed in backend root
- [ ] `firebase-admin` installed (`pip install firebase-admin`)
- [ ] Database tables created (`FCMToken`, `NotificationLog`)
- [ ] Firebase initialized in `app/__init__.py`
- [ ] `.gitignore` updated to exclude `serviceAccountKey.json`
- [ ] Backend server running without errors
- [ ] Frontend FCM integration completed
- [ ] Test notification sent successfully

## 🚀 You're Ready!

Your push notification system is now set up! Students will receive notifications when CRs send class updates.
