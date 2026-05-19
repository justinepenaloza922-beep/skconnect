# Attendance Tracking & QR Code Implementation Guide

## Overview
Complete attendance tracking system with QR code scanning, token generation, and reporting capabilities has been implemented for SK Connect Events & Projects module.

---

## ✅ What Has Been Implemented

### 1. **Backend API Endpoints** (app.py)
Added comprehensive endpoints for attendance management:

#### Fetch Attendance Records
```
GET /api/attendance/<event_id>
```
Returns all registrations and attendance stats for an event.

**Response:**
```json
{
  "success": true,
  "registrations": [
    {
      "id": 1,
      "event_id": 123,
      "full_name": "Juan Dela Cruz",
      "barangay": "Zone 1",
      "contact": "09123456789",
      "email": "juan@example.com",
      "attended": true,
      "attended_at": "2025-12-01T10:30:00",
      "registered_at": "2025-11-20T14:00:00"
    }
  ],
  "stats": {
    "total_registered": 24,
    "total_attended": 16,
    "total_pending": 8
  }
}
```

#### Update Attendance Status
```
PATCH /api/attendance/<event_id>/<registration_id>
```
Update individual attendance status (Present/Absent/Pending).

**Request Body:**
```json
{
  "status": "Present"
}
```

#### Generate QR Token
```
POST /api/event/<event_id>/generate-token
```
Generate unique QR code token for an event.

**Response:**
```json
{
  "success": true,
  "token": "abc123def456...",
  "qr_url": "http://localhost:5001/mark-attendance/123",
  "event_name": "Barangay Clean-up Drive"
}
```

#### Mark Attendance by Token
```
POST /api/attendance/mark
```
Admin API to mark attendance via scanned QR token.

**Request Body:**
```json
{
  "token": "abc123def456..."
}
```

#### Export Attendance Report
```
GET /api/attendance/<event_id>/export
```
Download attendance as CSV file.

---

### 2. **Event Creation Enhancement**
When creating events, the system now:
- Automatically generates unique QR tokens if "Generate QR code" is checked
- Stores tokens in `event_qr_tokens` table
- Associates tokens with events for easy tracking

---

### 3. **Frontend Features** (sk_connect_events_projects.html)

#### Attendance Modal
- **Dynamic Table Loading**: Automatically fetches and displays all registered participants
- **Real-time Status Updates**: Click checkboxes to mark attendance as Present/Absent
- **Live Statistics**: Shows total registered, present, absent, and pending counts
- **Status Badges**: Color-coded status indicators (green=present, yellow=pending)

#### QR Scanner
- **Integrated Camera Access**: `html5-qrcode` library for scanning
- **Token Extraction**: Automatically detects registration tokens from QR codes
- **Real-time Updates**: Attendance list updates immediately after scan
- **Error Handling**: User-friendly error messages

#### Export Functionality
- **CSV Export**: Download complete attendance records with one click
- **Includes**: Name, barangay, contact, email, registration date, attendance status, time marked

#### Actions Available
Each event row has buttons for:
- **View Details**: See full event information
- **Generate QR**: Create and download QR code image
- **Track Attendance**: Open attendance modal
- **Edit**: Modify event details

---

## 🔄 How It Works: End-to-End Flow

### For Registrants:
1. User registers for event → System generates registration token
2. Token is encoded in QR code → Shared with registrant
3. At event, registrant scans QR code or opens mark-attendance link
4. System records attendance in database

### For Admins:
1. Opens event row → Clicks "Track Attendance"
2. Attendance modal loads with all registered participants
3. Can manually check/uncheck boxes to mark attendance
4. Can scan QR codes to quickly mark attendance
5. Can download CSV report of attendance

---

## 📊 Database Schema

### event_registrations table
```sql
id - Primary key
event_id - Foreign key to events
full_name - Participant name
barangay - Barangay location
contact - Phone number
email - Email address
registration_token - Unique token for attendance
registered_at - Registration timestamp
attended - Boolean (true/false)
attended_at - When they marked attendance
marked_by - Admin user ID who marked attendance
```

### event_qr_tokens table (optional)
```sql
id - Primary key
event_id - Foreign key to events
qr_token - Unique token value
created_at - Creation timestamp
active - Boolean
```

### attendances table (generic)
```sql
id - Primary key
event_id - Foreign key to events
registration_id - Link to event_registrations
user_id - Link to user (if registered)
name - Name
email - Email
phone - Phone
barangay - Barangay
status - Present/Absent/Pending
marked_at - Timestamp
```

---

## 🚀 Usage Instructions

### Creating an Event with QR Tracking
1. Click "Create New Event"
2. Fill in event details
3. **Check** "Generate QR code for attendance tracking"
4. Click "Create Event"
5. QR code is automatically generated and stored

### Tracking Attendance
1. Find event in list
2. Click **"Track Attendance"** button (checkbox icon)
3. Modal opens showing all registered participants
4. **Option A - Manual**: Check/uncheck boxes to mark Present/Absent
5. **Option B - QR Scan**: Click "Scan QR" button, point camera at QR code
6. **Option C - Export**: Click "Export Report" to download CSV

### Generating QR Code
1. Click **Generate QR** button on event row (QR icon)
2. Modal shows QR code
3. Click **Download QR Code** to save as PNG
4. Share with participants or print for venue

---

## 🔧 Technical Details

### Dependencies Used
- **html5-qrcode@2.3.8**: Camera-based QR scanning
- **qrcodejs@1.0.0**: QR code generation
- **Supabase**: Backend database and real-time updates
- **Flask**: REST API endpoints

### API Response Standards
All endpoints follow consistent JSON response format:
```json
{
  "success": true/false,
  "data": { ... },
  "error": "Error message if applicable"
}
```

### Error Handling
- ✅ Camera permission denied → User-friendly message
- ✅ Invalid token → 404 with clear message
- ✅ Database errors → Logged server-side, user gets status message
- ✅ Network errors → Try-catch blocks with user alerts

---

## 📱 Mobile Support
- **Responsive Design**: Works on phone, tablet, desktop
- **Touch-friendly**: Large buttons and checkboxes for mobile
- **Camera Access**: Supports mobile device cameras
- **CSV Export**: Downloads to device storage

---

## 🔐 Security Considerations
- Attendance marking requires admin login (session check)
- Registration tokens are unique UUIDs (cryptographically secure)
- Attendance data is scoped to event_id (no cross-event access)
- Admin API endpoints validate admin session

---

## 📋 Checklist: What's Ready
- ✅ QR token generation in event creation
- ✅ QR code display and download functionality
- ✅ QR code scanner (camera-based)
- ✅ Attendance fetch API
- ✅ Attendance status update API
- ✅ Attendance export as CSV
- ✅ Real-time attendance table with live stats
- ✅ Manual attendance marking (checkboxes)
- ✅ Token-based attendance marking (API)
- ✅ Error handling and user feedback
- ✅ Responsive mobile design

---

## 🧪 Testing the Implementation

### Test QR Code Generation
```bash
# Navigate to: http://localhost:5001/admin_events_projects
# Click "Create New Event"
# Check "Generate QR code for attendance tracking"
# Create event and click "Generate QR" button
```

### Test Attendance Tracking
```bash
# Click "Track Attendance" on any event
# Attendance modal should load with registered participants
# Click checkboxes to mark Present/Absent
# Click "Scan QR" to test QR scanner
```

### Test CSV Export
```bash
# In attendance modal, click "Export Report"
# CSV file should download with all attendance data
```

### Test API Endpoints Directly
```bash
# Fetch attendance
curl -X GET http://localhost:5001/api/attendance/1

# Generate token
curl -X POST http://localhost:5001/api/event/1/generate-token

# Mark attendance
curl -X POST http://localhost:5001/api/attendance/mark \
  -H "Content-Type: application/json" \
  -d '{"token": "abc123..."}'

# Update status
curl -X PATCH http://localhost:5001/api/attendance/1/1 \
  -H "Content-Type: application/json" \
  -d '{"status": "Present"}'
```

---

## 🐛 Troubleshooting

### Issue: "Camera permission denied"
**Solution**: Browser needs camera permission. Check browser settings.

### Issue: QR scanner not working
**Solution**: Ensure HTTPS is used (or localhost). QRCode scanner requires secure context.

### Issue: Attendance modal doesn't show data
**Solution**: 
1. Check browser console for errors (F12)
2. Verify event has registered participants
3. Check Supabase connection status

### Issue: CSV export returns error
**Solution**:
1. Ensure event_id is valid
2. Check Supabase table permissions
3. Verify CSV export API is accessible

---

## 📞 Support

For issues or questions about this implementation:
1. Check server logs: `app.py` terminal output
2. Check browser console: F12 → Console tab
3. Verify Supabase connection and tables exist
4. Review network tab in DevTools for API responses

---

## 📝 Notes
- All timestamps are in UTC (converted to local timezone in UI)
- QR tokens are valid indefinitely (no expiration)
- Attendance is immutable once marked (update changes status only)
- CSV export includes all columns from event_registrations table

---

**Implementation Date**: December 1, 2025
**Status**: ✅ Complete and Ready for Use
