-- ============================================
-- SK Connect Document Management System
-- Table: documents
-- Purpose: Store metadata for uploaded documents and templates
-- ============================================

-- Create the documents table (if it doesn't exist)
CREATE TABLE IF NOT EXISTS public.documents (
    -- Primary key: UUID for unique identification
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,

    -- Document metadata
    title VARCHAR(255) NOT NULL,
    description TEXT,
    file_name VARCHAR(255) NOT NULL,
    file_url TEXT NOT NULL,
    file_type VARCHAR(100),
    file_size BIGINT,

    -- User and categorization
    uploaded_by VARCHAR(255),
    is_template BOOLEAN DEFAULT FALSE,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_documents_created_at ON public.documents (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_documents_is_template ON public.documents (is_template);
CREATE INDEX IF NOT EXISTS idx_documents_uploaded_by ON public.documents (uploaded_by);

-- FORCE DISABLE Row Level Security (RLS) for admin access
ALTER TABLE public.documents DISABLE ROW LEVEL SECURITY;

-- Drop ALL existing RLS policies (comprehensive cleanup)
DROP POLICY IF EXISTS "Enable all operations for authenticated users" ON public.documents;
DROP POLICY IF EXISTS "documents_select_policy" ON public.documents;
DROP POLICY IF EXISTS "documents_insert_policy" ON public.documents;
DROP POLICY IF EXISTS "documents_update_policy" ON public.documents;
DROP POLICY IF EXISTS "documents_delete_policy" ON public.documents;
DROP POLICY IF EXISTS "documents_all_policy" ON public.documents;
DROP POLICY IF EXISTS "authenticated_users_policy" ON public.documents;

-- Grant FULL permissions to authenticated users
GRANT SELECT, INSERT, UPDATE, DELETE ON public.documents TO authenticated;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO authenticated;

-- Add comments for documentation
COMMENT ON TABLE public.documents IS 'Stores metadata for uploaded documents and templates in SK Connect DMS';
COMMENT ON COLUMN public.documents.id IS 'Unique identifier for each document';
COMMENT ON COLUMN public.documents.title IS 'User-provided title for the document';
COMMENT ON COLUMN public.documents.description IS 'Optional description of the document content';
COMMENT ON COLUMN public.documents.file_name IS 'Original filename as uploaded by user';
COMMENT ON COLUMN public.documents.file_url IS 'Relative path to the stored file in static/uploads/documents/';
COMMENT ON COLUMN public.documents.file_type IS 'MIME type of the file (e.g., application/pdf, image/jpeg)';
COMMENT ON COLUMN public.documents.file_size IS 'Size of the file in bytes';
COMMENT ON COLUMN public.documents.uploaded_by IS 'Username or identifier of the person who uploaded the document';
COMMENT ON COLUMN public.documents.is_template IS 'Boolean flag: TRUE for document templates, FALSE for regular documents';
COMMENT ON COLUMN public.documents.created_at IS 'Timestamp when the document was uploaded';
COMMENT ON COLUMN public.documents.updated_at IS 'Timestamp when the document was last modified';

-- Verify the setup
SELECT
    schemaname,
    tablename,
    rowsecurity as rls_enabled,
    'Table created successfully' as status
FROM pg_tables
WHERE tablename = 'documents' AND schemaname = 'public';
