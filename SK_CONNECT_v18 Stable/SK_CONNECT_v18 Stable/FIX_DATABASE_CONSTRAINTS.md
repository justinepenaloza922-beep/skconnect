# 🔧 Fix Database Constraint Conflicts

## Issue
You're getting this error:
```
ERROR: 42710: constraint "fk_attendances_event" for relation "attendances" already exists
```

This means the constraint already exists in your database.

---

## ✅ Solution

### Option 1: Use IF NOT EXISTS (Recommended)
The `create_attendance_tables.sql` file has been updated to use `IF NOT EXISTS` for all constraints.

**Just run it again:**
```
Copy: sql/create_attendance_tables.sql
Paste into Supabase SQL Editor
Click RUN
```

It will now skip existing constraints safely.

---

### Option 2: Fix Existing Constraints
If you're still getting errors, run the cleanup script:

**Steps:**
1. Copy contents of: `sql/fix_constraints.sql`
2. Paste into Supabase SQL Editor
3. Click RUN

This script will:
- Drop existing constraints safely
- Recreate them cleanly
- Verify they're in place

---

### Option 3: Manual Check (If Needed)
If you want to verify what's already in your database:

```sql
-- Run this in Supabase SQL Editor to see existing constraints:
SELECT constraint_name, table_name, table_schema
FROM information_schema.table_constraints 
WHERE table_schema = 'public' 
AND constraint_name LIKE 'fk_%'
ORDER BY table_name;
```

---

## ✅ Status Check

To verify everything is set up correctly, run:

```sql
-- Check event_registrations table
SELECT * FROM information_schema.columns 
WHERE table_name = 'event_registrations' 
AND table_schema = 'public';

-- Check attendances table
SELECT * FROM information_schema.columns 
WHERE table_name = 'attendances' 
AND table_schema = 'public';

-- Check constraints
SELECT constraint_name, table_name 
FROM information_schema.table_constraints 
WHERE table_schema = 'public' 
AND constraint_name LIKE 'fk_%'
ORDER BY table_name;
```

---

## 🚀 What to Do Now

1. **Try running again** with updated SQL:
   - Copy `sql/create_attendance_tables.sql`
   - Paste into Supabase SQL Editor
   - Click RUN

2. **If still getting errors**, run:
   - Copy `sql/fix_constraints.sql`
   - Paste into Supabase SQL Editor
   - Click RUN

3. **Verify** using the status check SQL above

---

## ✨ Files Updated

- ✅ `sql/create_attendance_tables.sql` - Now uses `IF NOT EXISTS` for constraints
- ✅ `sql/fix_constraints.sql` - New file to clean up conflicts

---

## 💡 Why This Happened

Supabase may have partially created the tables or constraints from a previous attempt. The updated SQL now handles this gracefully by:
- Using `IF NOT EXISTS` for all DDL statements
- Safely creating only what's needed
- Skipping existing objects

---

**Try Option 1 first. It should work now!** ✅
