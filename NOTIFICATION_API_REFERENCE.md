# Push Notification API Quick Reference

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install firebase-admin
```

### 2. Add Service Account Key
- Download from Firebase Console → Project Settings → Service Accounts
- Save as `serviceAccountKey.json` in root directory
- **DO NOT commit to Git!** (already in .gitignore)

### 3. Create Tables
```python
python
>>> from app import create_app, db
>>> app = create_app()
>>> with app.app_context():
...     db.create_all()
>>> exit()
```

---

## 📡 API Endpoints

### 1️⃣ Register FCM Token
**When**: User logs in to the app

```javascript
// React Native Frontend
POST /api/notifications/register-token
{
  "email": "e230123@rguktrkv.ac.in",
  "fcm_token": "eXAmPLeToKeN...",
  "device_type": "android"  // or "ios"
}

// Response
{
  "success": true,
  "message": "FCM token registered successfully"
}
```

### 2️⃣ Send Notification (CR Only)
**When**: CR wants to send message to classmates

```javascript
// React Native Frontend
POST /api/cr/send-notification
{
  "cr_email": "cr@rguktrkv.ac.in",
  "title": "Class Update",
  "message": "Tomorrow's class at 9 AM in Lab 201"
}

// Response
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

### 3️⃣ Get Notification History
**When**: CR wants to see sent notifications

```javascript
// React Native Frontend
GET /api/notifications/history?cr_email=cr@rguktrkv.ac.in

// Response
{
  "success": true,
  "notifications": [
    {
      "id": 1,
      "title": "Class Update",
      "message": "Venue changed to Lab 201",
      "recipient_count": 43,
      "sent_at": "2025-10-07T10:30:00",
      "status": "success"
    }
  ]
}
```

---

## 🔐 Security Features

✅ **Email Domain Validation**: Only `@rguktrkv.ac.in` emails allowed
✅ **CR Authorization**: Only CRs can send notifications
✅ **Class-Level Isolation**: CRs can only message their own class
✅ **Student Verification**: Validates student exists in database

---

## 🧪 Testing

### Test with cURL

```bash
# 1. Register a token
curl -X POST http://localhost:5000/api/notifications/register-token \
  -H "Content-Type: application/json" \
  -d '{
    "email": "e230123@rguktrkv.ac.in",
    "fcm_token": "test_token_123",
    "device_type": "android"
  }'

# 2. Send notification (as CR)
curl -X POST http://localhost:5000/api/cr/send-notification \
  -H "Content-Type: application/json" \
  -d '{
    "cr_email": "cr@rguktrkv.ac.in",
    "title": "Test",
    "message": "Hello class!"
  }'
```

---

## 📱 React Native Integration

### Step 1: Install Firebase
```bash
npm install @react-native-firebase/app @react-native-firebase/messaging
```

### Step 2: Request Permission & Get Token
```javascript
import messaging from '@react-native-firebase/messaging';
import { Platform } from 'react-native';

const setupNotifications = async (userEmail) => {
  // Request permission
  const authStatus = await messaging().requestPermission();
  
  if (authStatus === messaging.AuthorizationStatus.AUTHORIZED) {
    // Get FCM token
    const fcmToken = await messaging().getToken();
    
    // Register with backend
    const response = await fetch(`${API_BASE_URL}/api/notifications/register-token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: userEmail,
        fcm_token: fcmToken,
        device_type: Platform.OS
      })
    });
    
    const data = await response.json();
    console.log('Token registered:', data);
  }
};
```

### Step 3: Handle Incoming Notifications
```javascript
import messaging from '@react-native-firebase/messaging';

// Foreground notifications
messaging().onMessage(async remoteMessage => {
  console.log('Notification received:', remoteMessage);
  // Show in-app notification
});

// Background/Quit notifications
messaging().setBackgroundMessageHandler(async remoteMessage => {
  console.log('Background notification:', remoteMessage);
});
```

### Step 4: CR Send Notification Screen
```javascript
const sendNotification = async () => {
  const response = await fetch(`${API_BASE_URL}/api/cr/send-notification`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      cr_email: userEmail,
      title: notificationTitle,
      message: notificationMessage
    })
  });
  
  const data = await response.json();
  
  if (data.success) {
    Alert.alert('Success', data.message);
  } else {
    Alert.alert('Error', data.error);
  }
};
```

---

## 🗃️ Database Tables

### FCMToken Table
```sql
id              INT (PK)
student_email   VARCHAR(255)
fcm_token       TEXT
device_type     VARCHAR(50)  -- 'android' or 'ios'
created_at      TIMESTAMP
updated_at      TIMESTAMP

UNIQUE(student_email, device_type)
```

### NotificationLog Table
```sql
id              INT (PK)
cr_email        VARCHAR(255)
title           VARCHAR(255)
message         TEXT
recipient_count INT
sent_at         TIMESTAMP
status          VARCHAR(50)  -- 'success', 'failed', 'partial'
```

---

## ⚠️ Common Errors

### "Firebase Admin SDK not installed"
```bash
pip install firebase-admin
```

### "Firebase credentials file not found"
- Download `serviceAccountKey.json` from Firebase Console
- Place in root directory (same level as `run.py`)

### "Not authorized. Only CRs can send notifications"
- Verify email is in CR table in database
- Check CR record exists with correct student_id

### "No students with registered devices found"
- Students must install app and login first
- FCM tokens are registered on app login

---

## 📊 Notification Data Structure

### Notification Payload
```javascript
{
  notification: {
    title: "Class Update",
    body: "Venue changed to Lab 201"
  },
  data: {
    type: "class_update",
    cr_name: "John Doe",
    cr_email: "cr@rguktrkv.ac.in",
    timestamp: "1696678800",
    year: "2",
    department: "CSE",
    section: "A"
  }
}
```

---

## ✅ Deployment Checklist

- [ ] Firebase project created
- [ ] Service account key downloaded
- [ ] `firebase-admin` installed
- [ ] Database tables created
- [ ] `.gitignore` updated
- [ ] Backend tested locally
- [ ] React Native Firebase configured
- [ ] Test notification sent successfully

---

## 🆘 Support

For issues:
1. Check console for Firebase initialization message
2. Verify `serviceAccountKey.json` exists
3. Ensure database tables are created
4. Test with cURL commands first
5. Check Firebase Console for project status

---

**Created**: October 7, 2025
**Last Updated**: October 7, 2025
