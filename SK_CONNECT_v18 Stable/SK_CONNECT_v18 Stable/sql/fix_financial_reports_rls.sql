-- Fix Row Level Security (RLS) policies for financial_reports table

-- Drop existing policies if they exist
DROP POLICY IF EXISTS "Allow authenticated users to view financial reports" ON public.financial_reports;
DROP POLICY IF EXISTS "Allow authenticated users to insert financial reports" ON public.financial_reports;
DROP POLICY IF EXISTS "Allow users to delete their own financial reports" ON public.financial_reports;
DROP POLICY IF EXISTS "Allow authenticated users to update financial reports" ON public.financial_reports;

-- Ensure RLS is enabled
ALTER TABLE public.financial_reports ENABLE ROW LEVEL SECURITY;

-- Policy 1: Allow authenticated users to SELECT (view) all financial reports
CREATE POLICY "allow_select_financial_reports"
  ON public.financial_reports
  FOR SELECT
  TO authenticated
  USING (true);

-- Policy 2: Allow authenticated users to INSERT (upload) financial reports
CREATE POLICY "allow_insert_financial_reports"
  ON public.financial_reports
  FOR INSERT
  TO authenticated
  WITH CHECK (true);

-- Policy 3: Allow authenticated users to UPDATE financial reports
CREATE POLICY "allow_update_financial_reports"
  ON public.financial_reports
  FOR UPDATE
  TO authenticated
  USING (true)
  WITH CHECK (true);

-- Policy 4: Allow authenticated users to DELETE financial reports
CREATE POLICY "allow_delete_financial_reports"
  ON public.financial_reports
  FOR DELETE
  TO authenticated
  USING (true);

-- Allow service role (server-side) to do everything
CREATE POLICY "allow_service_role"
  ON public.financial_reports
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

-- Grant permissions to authenticated users
GRANT SELECT, INSERT, UPDATE, DELETE ON public.financial_reports TO authenticated;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO authenticated;
