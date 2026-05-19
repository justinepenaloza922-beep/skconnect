-- Disable RLS on financial_reports table
-- This is the simplest solution for allowing all authenticated users to access the table

ALTER TABLE public.financial_reports DISABLE ROW LEVEL SECURITY;

-- Drop all existing policies
DROP POLICY IF EXISTS "Allow authenticated users to view financial reports" ON public.financial_reports;
DROP POLICY IF EXISTS "Allow authenticated users to insert financial reports" ON public.financial_reports;
DROP POLICY IF EXISTS "Allow users to delete their own financial reports" ON public.financial_reports;
DROP POLICY IF EXISTS "Allow authenticated users to update financial reports" ON public.financial_reports;
DROP POLICY IF EXISTS "allow_select_financial_reports" ON public.financial_reports;
DROP POLICY IF EXISTS "allow_insert_financial_reports" ON public.financial_reports;
DROP POLICY IF EXISTS "allow_update_financial_reports" ON public.financial_reports;
DROP POLICY IF EXISTS "allow_delete_financial_reports" ON public.financial_reports;
DROP POLICY IF EXISTS "allow_service_role" ON public.financial_reports;

-- Grant permissions to authenticated users (no RLS needed)
GRANT SELECT, INSERT, UPDATE, DELETE ON public.financial_reports TO authenticated;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO authenticated;

-- Optional: Grant permissions to anon role if you want public access
-- GRANT SELECT ON public.financial_reports TO anon;
