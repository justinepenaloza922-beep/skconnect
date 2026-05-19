# 🔧 Database Constraint Fix - Complete Guide

## The Problem
```
ERROR: 42710: constraint "fk_attendances_event" for relation "attendances" already exists
```

This error means one or more foreign key constraints already exist in your database.

---

## Quick Fix (5 Minutes)

### Step 1: Use the Updated SQL File
The main SQL file has been updated with `IF NOT EXISTS` clauses. This makes it safe to run multiple times.

**To apply:**
1. Open Supabase SQL Editor
2. Copy from: `sql/create_attendance_tables.sql`
3. Paste into SQL Editor
4. Click **RUN**

**Result:** It will skip constraints that already exist and create any missing ones.

---

## If Step 1 Doesn't Work (10 Minutes)

### Step 2: Run the Cleanup Script

The cleanup script (`sql/fix_constraints.sql`) will:
1. Drop existing constraints safely
2. Recreate them cleanly
3. Show verification results

**To apply:**
1. Open Supabase SQL Editor
2. Copy from: `sql/fix_constraints.sql`
3. Paste into SQL Editor
4. Click **RUN**

**Result:** All constraints will be recreated properly.

---

## Verify the Fix (2 Minutes)

Run this verification script to check everything is correct:

1. Open Supabase SQL Editor
2. Copy from: `sql/verify_setup.sql`
3. Paste into SQL Editor
4. Click **RUN**

**You should see:**
✅ event_registrations table exists
✅ attendances table exists
✅ Foreign key constraints are in place
✅ Indexes are created
✅ All tables are accessible

---

## Understanding the Issue

### Why Did This Happen?
- Previous migration may have partially completed
- Tables were created but constraints already existed
- Supabase doesn't allow duplicate constraint names

### Why the Fix Works
- **IF NOT EXISTS** checks if constraint exists before creating
- **DROP IF EXISTS** safely removes constraints before recreating
- **Error handling** allows script to continue if one statement fails

---

## File Changes Made

### Updated Files ✅
1. **sql/create_attendance_tables.sql**
   - Added `IF NOT EXISTS` to all ALTER TABLE ADD CONSTRAINT statements
   - Makes file idempotent (safe to run multiple times)

### New Files Created ✅
2. **sql/fix_constraints.sql**
   - Safely drops existing constraints
   - Recreates them cleanly
   - Includes verification query

3. **sql/verify_setup.sql**
   - Checks all tables exist
   - Verifies constraints are in place
   - Verifies indexes are created
   - Shows data counts

4. **FIX_DATABASE_CONSTRAINTS.md**
   - This comprehensive guide

---

## Step-by-Step Instructions

### Option A: Clean Install (Recommended)
```
1. Go to Supabase Dashboard
2. SQL Editor
3. Copy: sql/fix_constraints.sql
4. Paste and RUN
5. Copy: sql/verify_setup.sql
6. Paste and RUN
7. Check all ✅ signs
```

### Option B: Safe Update
```
1. Go to Supabase Dashboard
2. SQL Editor
3. Copy: sql/create_attendance_tables.sql (updated version)
4. Paste and RUN
5. Should now work without errors
```

### Option C: Check Current State
```
1. Go to Supabase Dashboard
2. SQL Editor
3. Copy: sql/verify_setup.sql
4. Paste and RUN
5. See what exists in database
6. Decide what action to take
```

---

## Expected Results

### After Running fix_constraints.sql
You'll see output showing:
- Constraint drops (if they existed)
- New constraint creation
- Verification query results

### After Running verify_setup.sql
You'll see:
```
✅ event_registrations table | column_count: 12
✅ attendances table | column_count: 9
✅ event_qr_tokens table | column_count: 7

✅ Constraints:
   fk_event_registrations_event
   fk_event_registrations_marked_by
   fk_attendances_event
   fk_attendances_registration
   fk_attendances_user

✅ Indexes:
   idx_event_registrations_token
   idx_event_registrations_event_id
   idx_attendances_event_id
   idx_attendances_user_id
   idx_attendances_marked_at
```

---

## Troubleshooting

### If You Still Get "Constraint Exists" Error
```
1. Run sql/fix_constraints.sql (clears old constraints)
2. Then run sql/create_attendance_tables.sql (recreates)
3. Then run sql/verify_setup.sql (confirm)
```

### If "Table Doesn't Exist" Error
```
1. The tables haven't been created yet
2. Run sql/create_attendance_tables.sql
3. Run sql/verify_setup.sql to confirm
```

### If You See Different Constraint Names
```
1. That's OK - they may have been created differently
2. You can safely have both old and new constraints
3. Just make sure foreign keys work (verify_setup.sql will show)
```

### If Constraints Can't Drop
```
1. Run sql/create_attendance_tables.sql (will use IF NOT EXISTS)
2. This will skip the ones that exist
3. Don't worry about dropping them manually
```

---

## What These Scripts Do

### create_attendance_tables.sql
Creates tables if they don't exist, with IF NOT EXISTS clauses.

**Safe to run multiple times** - will skip existing objects.

### fix_constraints.sql
Drops and recreates all constraints cleanly.

**Use if you get constraint conflicts.**

### verify_setup.sql
Shows the current state of your database.

**Use to confirm everything is set up correctly.**

---

## Database Table Reference

### event_registrations
```
Stores when people register for events
Columns: id, event_id, full_name, barangay, contact, email, 
         registration_token, registered_at, attended, attended_at, 
         marked_by, created_at
Foreign Keys: event_id → events.id
              marked_by → skc_users.id
```

### attendances
```
Generic attendance records (guest/manual/scanned entries)
Columns: id, event_id, registration_id, user_id, name, email, 
         phone, barangay, status, marked_at, created_at
Foreign Keys: event_id → events.id
              registration_id → event_registrations.id
              user_id → skc_users.id
```

### event_qr_tokens (Optional)
```
Tracks QR tokens generated for events
Columns: id, event_id, qr_token, created_at, active, generated_by
Foreign Keys: event_id → events.id
              generated_by → skc_users.id
```

---

## Checklist

- [ ] Read this guide
- [ ] Choose Option A, B, or C above
- [ ] Run the SQL script(s)
- [ ] Run verify_setup.sql to confirm
- [ ] See all ✅ signs
- [ ] System ready to use!

---

## Next Steps

After fixing the database:

1. ✅ Run the verification script
2. ✅ Restart Flask app
3. ✅ Test the attendance features
4. ✅ All systems should work!

---

## Support

If you still have issues:
1. Run `sql/verify_setup.sql`
2. Check the output carefully
3. See if any constraints are missing
4. If needed, run `sql/fix_constraints.sql` again

---

**The constraint error should be resolved now!** ✅

Try running the SQL script again - it should work.
