# Attendance Tracking - Setup Guide

## Prerequisites
- Flask application running
- Supabase project with events table
- Tables already created (see below)

---

## 1. Create Required Database Tables

### In Supabase Dashboard:
1. Go to **SQL Editor** in Supabase Console
2. Copy the contents of `/sql/create_attendance_tables.sql`
3. Paste into SQL editor
4. Click **Run**

This creates:
- `event_registrations` - Main table for tracking participant attendance
- `attendances` - Generic attendance records

### Optional: Create QR Tokens Tracking Table
1. Copy contents of `/sql/optional_qr_tokens_table.sql`
2. Paste into SQL editor
3. Click **Run**

This creates:
- `event_qr_tokens` - Track which tokens were generated for which events

---

## 2. Verify Table Permissions

Ensure your Supabase anon key (public) has the following permissions:

**event_registrations**
- ✅ SELECT (read all registrations)
- ✅ INSERT (create new registrations)
- ✅ UPDATE (mark attendance)

**attendances**
- ✅ SELECT (read records)
- ✅ INSERT (create new records)
- ✅ UPDATE (change status)

**event_qr_tokens** (if created)
- ✅ SELECT
- ✅ INSERT
- ✅ UPDATE

### To Check/Set Permissions:
1. In Supabase, go to **Authentication** → **Policies**
2. For each table, ensure Row Level Security (RLS) allows operations
3. Or disable RLS for development (less secure, but simpler for testing)

---

## 3. Update Events Table (Optional)

If you want to store the QR token directly on the event:

```sql
ALTER TABLE public.events ADD COLUMN IF NOT EXISTS qr_token text;
ALTER TABLE public.events ADD COLUMN IF NOT EXISTS enable_qr boolean DEFAULT false;
```

---

## 4. Environment Variables

Verify `.env` file contains:

```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key
```

---

## 5. Test the Implementation

### A. Create an Event with QR Code
```bash
# Start Flask app
python app.py

# Navigate to: http://localhost:5001/admin_events_projects
# Click "Create New Event"
# Check "Generate QR code for attendance tracking"
# Fill in other details and click "Create Event"
```

### B. Test Attendance Tracking
```bash
# Event should now appear in the list
# Click "Track Attendance" button
# You should see attendance modal with any registered participants
```

### C. Test QR Code Generation
```bash
# Click "Generate QR" button on event row
# QR code modal should appear
# Click "Download QR Code" to save as image
```

### D. Test CSV Export
```bash
# Open attendance modal
# Click "Export Report"
# CSV file should download automatically
```

---

## 6. API Testing

### Get Attendance for Event
```bash
curl -X GET http://localhost:5001/api/attendance/1 \
  -H "Content-Type: application/json"
```

### Mark Attendance by Token
```bash
curl -X POST http://localhost:5001/api/attendance/mark \
  -H "Content-Type: application/json" \
  -d '{"token": "your-token-here"}'
```

### Update Attendance Status
```bash
curl -X PATCH http://localhost:5001/api/attendance/1/1 \
  -H "Content-Type: application/json" \
  -d '{"status": "Present"}'
```

### Export as CSV
```bash
curl -X GET http://localhost:5001/api/attendance/1/export \
  > attendance.csv
```

---

## 7. Troubleshooting

### "Table doesn't exist" error
**Solution**: Run the SQL migration in Supabase SQL editor

### "Permission denied" error
**Solution**: 
1. Check Supabase RLS policies
2. Verify anon key has correct permissions
3. Or disable RLS for tables (development only)

### QR Scanner not working
**Solution**:
1. App must be accessed over HTTPS (or localhost)
2. Browser must grant camera permission
3. Check browser console for errors (F12)

### Attendance not updating
**Solution**:
1. Verify event_id is correct
2. Check Supabase network tab in browser DevTools
3. Ensure user is logged in (for admin functions)

---

## 8. Production Deployment

### Before deploying:
1. ✅ Test all attendance flows locally
2. ✅ Enable RLS on Supabase tables
3. ✅ Set up proper authentication policies
4. ✅ Configure HTTPS (required for camera access)
5. ✅ Set secure secret key in Flask
6. ✅ Test CSV export functionality
7. ✅ Monitor error logs

### Deployment Steps:
1. Deploy Flask app to production server
2. Ensure Supabase URL and key are set in environment
3. Test each endpoint before announcing to users
4. Monitor logs for errors
5. Train admins on attendance tracking workflow

---

## 9. Features Overview

| Feature | Status | Notes |
|---------|--------|-------|
| QR Code Generation | ✅ | Automatic on event creation |
| QR Code Download | ✅ | PNG format, downloadable |
| QR Code Scanning | ✅ | Camera-based, real-time |
| Manual Attendance | ✅ | Checkbox-based marking |
| CSV Export | ✅ | All fields included |
| Real-time Stats | ✅ | Updates on every change |
| Mobile Support | ✅ | Fully responsive |
| Admin Only | ✅ | Session-based access control |

---

## 10. Example Workflow

### For Admins
1. **Create Event** → System generates QR token
2. **Download QR** → Print or share with participants
3. **At Event** → Open attendance modal
4. **Mark Attendance** → Scan QR codes or manually check boxes
5. **View Stats** → Live count of Present/Absent/Pending
6. **Export Report** → Download CSV for records

### For Participants
1. **Register** → Receive registration token in email/SMS
2. **At Event** → Scan QR code or open mark-attendance link
3. **Confirm** → Click button to mark attendance
4. **Done** → Attendance is recorded

---

## 11. Database Backup

### To backup attendance data:
```sql
-- Export registrations
SELECT * FROM public.event_registrations 
ORDER BY event_id, registered_at DESC;

-- Export attendances
SELECT * FROM public.attendances 
ORDER BY event_id, marked_at DESC;
```

### To restore from CSV:
```sql
COPY event_registrations FROM 'attendance.csv' WITH (FORMAT csv, HEADER);
```

---

## Support & Next Steps

### Recommended Enhancements:
1. **SMS Notifications**: Notify admins when QR is scanned
2. **Email Reports**: Auto-email attendance reports
3. **Check-in Badges**: Generate attendance badges for print
4. **Duplicate Detection**: Prevent marking same person twice
5. **Time-based Tracking**: Track check-in times
6. **Department Filtering**: Filter by department/volunteer type

### Contact
For issues or feature requests, refer to the main `ATTENDANCE_IMPLEMENTATION.md` guide.

---

**Last Updated**: December 1, 2025
**Version**: 1.0 - Initial Release
