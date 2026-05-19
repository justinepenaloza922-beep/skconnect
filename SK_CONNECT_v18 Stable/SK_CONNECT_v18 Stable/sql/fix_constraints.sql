-- Safe migration script: Run this if you encounter constraint conflicts
-- This script drops and recreates constraints safely

-- Drop existing constraints if they exist (PostgreSQL)
DO $$ 
BEGIN
  BEGIN
    ALTER TABLE IF EXISTS public.attendances DROP CONSTRAINT IF EXISTS fk_attendances_event;
  EXCEPTION WHEN OTHERS THEN NULL;
  END;
  
  BEGIN
    ALTER TABLE IF EXISTS public.attendances DROP CONSTRAINT IF EXISTS fk_attendances_registration;
  EXCEPTION WHEN OTHERS THEN NULL;
  END;
  
  BEGIN
    ALTER TABLE IF EXISTS public.attendances DROP CONSTRAINT IF EXISTS fk_attendances_user;
  EXCEPTION WHEN OTHERS THEN NULL;
  END;
  
  BEGIN
    ALTER TABLE IF EXISTS public.event_registrations DROP CONSTRAINT IF EXISTS fk_event_registrations_event;
  EXCEPTION WHEN OTHERS THEN NULL;
  END;
  
  BEGIN
    ALTER TABLE IF EXISTS public.event_registrations DROP CONSTRAINT IF EXISTS fk_event_registrations_marked_by;
  EXCEPTION WHEN OTHERS THEN NULL;
  END;
END $$;

-- Now recreate them cleanly
ALTER TABLE IF EXISTS public.event_registrations
  ADD CONSTRAINT fk_event_registrations_event
  FOREIGN KEY (event_id) REFERENCES public.events(id) ON DELETE CASCADE;

ALTER TABLE IF EXISTS public.event_registrations
  ADD CONSTRAINT fk_event_registrations_marked_by
  FOREIGN KEY (marked_by) REFERENCES public.skc_users(id) ON DELETE SET NULL;

ALTER TABLE IF EXISTS public.attendances
  ADD CONSTRAINT fk_attendances_event
  FOREIGN KEY (event_id) REFERENCES public.events(id) ON DELETE CASCADE;

ALTER TABLE IF EXISTS public.attendances
  ADD CONSTRAINT fk_attendances_registration
  FOREIGN KEY (registration_id) REFERENCES public.event_registrations(id) ON DELETE SET NULL;

ALTER TABLE IF EXISTS public.attendances
  ADD CONSTRAINT fk_attendances_user
  FOREIGN KEY (user_id) REFERENCES public.skc_users(id) ON DELETE SET NULL;

-- Verify constraints are in place
SELECT constraint_name, table_name 
FROM information_schema.table_constraints 
WHERE table_schema = 'public' 
AND constraint_name LIKE 'fk_%'
ORDER BY table_name;
