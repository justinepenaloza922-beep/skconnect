# Attendance Tracking Quick Reference

## 🎯 What You Can Do Now

### Admin Functions
| Action | Steps | Result |
|--------|-------|--------|
| **Create Event with QR** | New Event → Check QR option → Create | Event gets unique QR token |
| **Generate QR Code** | Event list → Generate QR button | QR modal appears, can download |
| **Track Attendance** | Event list → Track Attendance button | Modal shows all participants |
| **Mark Present** | Attendance modal → Check box | Changes status to Present |
| **Mark Absent** | Attendance modal → Uncheck box | Changes status to Absent |
| **Scan QR** | Attendance modal → Scan QR button | Open camera, point at QR code |
| **Export Report** | Attendance modal → Export Report button | Download CSV file |

---

## 📱 How Participants Mark Attendance

### Option 1: Scan QR Code
1. Get QR code from admin
2. Open camera
3. Point at QR code
4. Tap "Confirm Attendance"
5. ✅ Attendance marked

### Option 2: Manual Link
1. Receive mark-attendance link via email
2. Click link on phone
3. Enter name (pre-filled if logged in)
4. Click "Submit Attendance"
5. ✅ Attendance marked

---

## 🔌 API Endpoints (for developers)

```
GET  /api/attendance/<event_id>              # Fetch all attendance
POST /api/attendance/mark                     # Mark by token
PATCH /api/attendance/<event_id>/<reg_id>    # Update status
GET  /api/attendance/<event_id>/export        # Download CSV
POST /api/event/<event_id>/generate-token     # Generate QR token
```

---

## 📊 Live Statistics

Attendance modal shows:
- **Total Registered**: How many signed up
- **Present**: Marked as attended
- **Absent**: Marked as not attended
- **Pending**: Not yet marked

Updates in real-time as you check/uncheck boxes or scan QR codes.

---

## 🎨 User Interface Locations

### In Events List
- **Generate QR** 🔲 (QR icon) - Generates QR code
- **Track Attendance** ✓ (checkmark icon) - Opens attendance modal
- **View Details** 👁️ (eye icon) - Shows event info
- **Edit** ✏️ (pencil icon) - Modify event

### In Attendance Modal
- **Scan QR** - Camera-based scanning
- **Export Report** - Download CSV
- **Checkboxes** - Mark Present (checked) / Absent (unchecked)
- **Search** - Find participant by name
- **Filter** - Show All/Present/Absent

---

## 💾 Data Storage

All attendance data is stored in Supabase:

**event_registrations table:**
- Participant info (name, email, phone, barangay)
- Registration token (unique identifier)
- Attended status (true/false)
- Timestamps (registered, attended)

**attendances table:**
- Generic attendance records
- Status tracking (Present/Absent/Pending)
- Multiple ways to link records

---

## 🔐 Access Control

| Role | Can Do |
|------|--------|
| **Admin (Logged In)** | Create events, track attendance, scan QR, export reports |
| **Participant** | Register, scan QR, mark own attendance |
| **Guest** | Mark attendance if has token/link |

---

## ⚙️ Requirements

✅ Browser with camera (for QR scanning)
✅ Internet connection
✅ Supabase project with tables created
✅ Flask app running
✅ Admin login (for admin functions)

---

## 📞 Quick Fixes

| Problem | Solution |
|---------|----------|
| Camera not working | Check browser permissions, try HTTPS |
| Attendance not loading | Refresh page, check internet |
| QR code won't scan | Better lighting, clean camera lens |
| CSV not downloading | Check browser download settings |
| Changes not saving | Check Supabase connection, try again |

---

## 📈 Key Statistics

- **QR Code** 📊 Unique per event (36 character hex)
- **Attendance Records** 💾 Stored indefinitely in Supabase
- **CSV Export** 📁 Includes all registration & attendance fields
- **Real-time Updates** ⚡ Changes visible immediately
- **Mobile Support** 📱 Full support for phones/tablets

---

## 🚀 Next Steps

1. ✅ Check that Supabase tables are created
2. ✅ Create test event with QR enabled
3. ✅ Test QR code generation and download
4. ✅ Test attendance tracking modal
5. ✅ Test QR scanning (if camera available)
6. ✅ Test CSV export
7. ✅ Train admins on the system
8. ✅ Train participants on QR process

---

## 📚 Documentation Files

| File | Purpose |
|------|---------|
| `ATTENDANCE_IMPLEMENTATION.md` | Complete technical documentation |
| `SETUP_GUIDE.md` | Step-by-step setup instructions |
| `QUICK_REFERENCE.md` | This file - quick commands |

---

## 🎓 Example Commands

### Create event with QR (via UI)
```
1. Click "Create New Event"
2. Fill details
3. ✅ Check "Generate QR code"
4. Click "Create Event"
```

### Mark attendance via API (advanced)
```bash
curl -X POST http://localhost:5001/api/attendance/mark \
  -H "Content-Type: application/json" \
  -d '{"token": "a1b2c3d4..."}'
```

### Export as CSV (via UI)
```
1. Open Event
2. Click "Track Attendance"
3. Click "Export Report"
4. CSV downloads automatically
```

---

## ✨ Features at a Glance

- ✅ QR Code Generation
- ✅ QR Code Scanning
- ✅ Manual Attendance Marking
- ✅ Real-time Statistics
- ✅ CSV Export
- ✅ Responsive Mobile Design
- ✅ Error Handling
- ✅ Admin Only Access
- ✅ Token-based Registration
- ✅ Time Tracking

---

**Implementation Status**: ✅ COMPLETE
**Last Updated**: December 1, 2025
**Version**: 1.0
