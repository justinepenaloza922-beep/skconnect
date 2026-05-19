-- Add volunteer hour tracking fields to support user dashboard volunteer hours aggregation
-- Run this in Supabase SQL editor or via psql connected to your project database.

ALTER TABLE IF EXISTS public.volunteer_signups
ADD COLUMN IF NOT EXISTS hours_logged numeric(6,2) DEFAULT 0 NOT NULL;

COMMENT ON COLUMN public.volunteer_signups.hours_logged IS 'Logged volunteer hours for this signup record';

-- Optional: also store hours directly on attendance records if you want to track hours per attendance event.
ALTER TABLE IF EXISTS public.attendances
ADD COLUMN IF NOT EXISTS hours_logged numeric(6,2) DEFAULT 0 NOT NULL;

COMMENT ON COLUMN public.attendances.hours_logged IS 'Logged volunteer hours for this attendance record';
