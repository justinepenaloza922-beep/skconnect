-- ============================================
-- FIX RLS ISSUES FOR DOCUMENTS TABLE
-- Run this if you get RLS policy violations
-- ============================================

-- Disable Row Level Security
ALTER TABLE public.documents DISABLE ROW LEVEL SECURITY;

-- Drop any existing RLS policies
DROP POLICY IF EXISTS "Enable all operations for authenticated users" ON public.documents;
DROP POLICY IF EXISTS "documents_select_policy" ON public.documents;
DROP POLICY IF EXISTS "documents_insert_policy" ON public.documents;
DROP POLICY IF EXISTS "documents_update_policy" ON public.documents;
DROP POLICY IF EXISTS "documents_delete_policy" ON public.documents;
DROP POLICY IF EXISTS "documents_all_policy" ON public.documents;

-- Grant permissions to authenticated users
GRANT SELECT, INSERT, UPDATE, DELETE ON public.documents TO authenticated;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO authenticated;

-- Verify RLS is disabled
SELECT schemaname, tablename, rowsecurity
FROM pg_tables
WHERE tablename = 'documents' AND schemaname = 'public';