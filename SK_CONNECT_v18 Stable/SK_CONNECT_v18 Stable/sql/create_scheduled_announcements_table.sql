-- Migration: create scheduled_announcements table
CREATE TABLE IF NOT EXISTS public.scheduled_announcements (
  id serial PRIMARY KEY,
  title text NOT NULL,
  description text,
  type text,
  created_at timestamptz NOT NULL DEFAULT now(),
  send_notification boolean DEFAULT false,
  schedule_post boolean DEFAULT false,
  schedule_time timestamptz,
  processed boolean DEFAULT false
);

-- Enable row-level security and allow anonymous and authenticated clients to use the table
ALTER TABLE public.scheduled_announcements ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow read for anon and authenticated" ON public.scheduled_announcements
  FOR SELECT
  TO authenticated, anon
  USING (true);

CREATE POLICY "Allow insert for anon and authenticated" ON public.scheduled_announcements
  FOR INSERT
  TO authenticated, anon
  WITH CHECK (true);

CREATE POLICY "Allow update for anon and authenticated" ON public.scheduled_announcements
  FOR UPDATE
  TO authenticated, anon
  USING (true)
  WITH CHECK (true);
