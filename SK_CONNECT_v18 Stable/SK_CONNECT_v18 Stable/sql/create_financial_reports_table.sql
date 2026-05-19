-- Create financial_reports table for storing uploaded financial reports
CREATE TABLE IF NOT EXISTS public.financial_reports (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  title VARCHAR(255) NOT NULL,
  report_type VARCHAR(50) CHECK (report_type IN ('quarterly', 'annual', 'project', 'audit', 'budget')),
  description TEXT,
  file_url TEXT NOT NULL,
  uploaded_by VARCHAR(255),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create an index on created_at for faster sorting
CREATE INDEX IF NOT EXISTS idx_financial_reports_created_at ON public.financial_reports(created_at DESC);

-- Create an index on report_type for filtering
CREATE INDEX IF NOT EXISTS idx_financial_reports_type ON public.financial_reports(report_type);

-- Create an index on uploaded_by for user-specific queries
CREATE INDEX IF NOT EXISTS idx_financial_reports_uploaded_by ON public.financial_reports(uploaded_by);

-- Enable RLS (Row Level Security)
ALTER TABLE public.financial_reports ENABLE ROW LEVEL SECURITY;

-- Policy: Allow authenticated users to view all financial reports
CREATE POLICY "Allow authenticated users to view financial reports"
  ON public.financial_reports
  FOR SELECT
  USING (auth.role() = 'authenticated');

-- Policy: Allow authenticated users to insert financial reports
CREATE POLICY "Allow authenticated users to insert financial reports"
  ON public.financial_reports
  FOR INSERT
  WITH CHECK (auth.role() = 'authenticated');

-- Policy: Allow users to delete their own financial reports (admins can delete any)
CREATE POLICY "Allow users to delete their own financial reports"
  ON public.financial_reports
  FOR DELETE
  USING (
    auth.role() = 'authenticated' AND (
      uploaded_by = auth.jwt() ->> 'sub' OR
      auth.jwt() ->> 'user_role' = 'sadmin'
    )
  );

-- Policy: Allow authenticated users to update financial reports
CREATE POLICY "Allow authenticated users to update financial reports"
  ON public.financial_reports
  FOR UPDATE
  USING (auth.role() = 'authenticated');

-- Add comment to table
COMMENT ON TABLE public.financial_reports IS 'Stores uploaded financial reports with metadata for the SK Connect platform';
COMMENT ON COLUMN public.financial_reports.id IS 'Unique identifier for the report';
COMMENT ON COLUMN public.financial_reports.title IS 'Title of the financial report';
COMMENT ON COLUMN public.financial_reports.report_type IS 'Type of report (quarterly, annual, project, audit, or budget)';
COMMENT ON COLUMN public.financial_reports.description IS 'Optional description of the report content';
COMMENT ON COLUMN public.financial_reports.file_url IS 'Path to the uploaded file';
COMMENT ON COLUMN public.financial_reports.uploaded_by IS 'User ID of who uploaded the report';
COMMENT ON COLUMN public.financial_reports.created_at IS 'Timestamp when the report was uploaded';
COMMENT ON COLUMN public.financial_reports.updated_at IS 'Timestamp of last update';
