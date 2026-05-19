-- Verify all attendance tracking tables and constraints are properly set up
-- Run this in Supabase SQL Editor to check your database status

-- ========== TABLE CHECKS ==========

-- 1. Check if event_registrations table exists and has all columns
SELECT 
  table_name,
  COUNT(*) as column_count
FROM information_schema.columns
WHERE table_name = 'event_registrations' 
AND table_schema = 'public'
GROUP BY table_name;

-- 2. Check if attendances table exists and has all columns
SELECT 
  table_name,
  COUNT(*) as column_count
FROM information_schema.columns
WHERE table_name = 'attendances' 
AND table_schema = 'public'
GROUP BY table_name;

-- 3. Check if event_qr_tokens table exists (optional)
SELECT 
  table_name,
  COUNT(*) as column_count
FROM information_schema.columns
WHERE table_name = 'event_qr_tokens' 
AND table_schema = 'public'
GROUP BY table_name;

-- ========== CONSTRAINT CHECKS ==========

-- 4. List all foreign key constraints
SELECT 
  constraint_name,
  table_name,
  column_name
FROM information_schema.key_column_usage
WHERE table_schema = 'public'
AND constraint_name LIKE 'fk_%'
ORDER BY table_name, constraint_name;

-- 5. Check all indexes
SELECT 
  tablename,
  indexname
FROM pg_indexes
WHERE schemaname = 'public'
AND (tablename = 'event_registrations' 
  OR tablename = 'attendances'
  OR tablename = 'event_qr_tokens')
ORDER BY tablename, indexname;

-- ========== DATA CHECKS ==========

-- 6. Check if tables have any data
SELECT 
  'event_registrations' as table_name,
  COUNT(*) as row_count
FROM public.event_registrations

UNION ALL

SELECT 
  'attendances' as table_name,
  COUNT(*) as row_count
FROM public.attendances

UNION ALL

SELECT 
  'event_qr_tokens' as table_name,
  COUNT(*) as row_count
FROM public.event_qr_tokens;

-- ========== SUMMARY ==========

-- 7. Show all tables starting with 'event' or 'attendance'
SELECT 
  tablename
FROM pg_tables
WHERE schemaname = 'public'
AND (tablename LIKE 'event%' OR tablename LIKE 'attendance%')
ORDER BY tablename;

-- ========== IF ALL LOOKS GOOD ==========
-- You should see:
-- ✅ event_registrations table with 12+ columns
-- ✅ attendances table with 9+ columns  
-- ✅ Multiple foreign key constraints (fk_%)
-- ✅ Multiple indexes (idx_%)
-- ✅ All tables have 0 rows (if just created) or data (if in use)

-- ========== IF YOU SEE ERRORS ==========
-- Run: sql/fix_constraints.sql
-- Then run this verification script again
