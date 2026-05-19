-- Migration: add tracking columns to announcements
-- Run this in your Supabase SQL editor / psql

ALTER TABLE public.announcements
  ADD COLUMN IF NOT EXISTS views integer DEFAULT 0,
  ADD COLUMN IF NOT EXISTS notifications_sent integer DEFAULT 0,
  ADD COLUMN IF NOT EXISTS scheduled_sent boolean DEFAULT false;

-- Optional: backfill NULLs to 0/false
UPDATE public.announcements SET views = COALESCE(views,0), notifications_sent = COALESCE(notifications_sent,0), scheduled_sent = COALESCE(scheduled_sent,false);

-- Verify
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='announcements' AND column_name IN ('views','notifications_sent','scheduled_sent');
