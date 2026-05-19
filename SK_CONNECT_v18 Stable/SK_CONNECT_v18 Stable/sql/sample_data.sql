-- Sample data for testing user dashboard
-- Run this in Supabase SQL Editor after setting up the database schema

-- Insert sample announcements
INSERT INTO public.announcements (title, description, created_at) VALUES
('Welcome to SK Connect!', 'Welcome to the new SK Connect platform. Stay updated with all community activities and events.', NOW()),
('Youth Summit 2026', 'Join us for the annual Youth Summit featuring workshops, networking, and fun activities.', NOW() - INTERVAL '2 days'),
('Community Clean-up Drive', 'Help keep our barangay clean! Join the clean-up drive this Saturday at the plaza.', NOW() - INTERVAL '1 day');

-- Insert sample events
INSERT INTO public.events (name, description, date, location, start_time, created_at) VALUES
('Youth Leadership Workshop', 'Learn essential leadership skills for community involvement.', '2026-05-15', 'Barangay Hall', '09:00:00', NOW()),
('Sports Festival', 'Annual sports competition featuring basketball, volleyball, and more.', '2026-05-20', 'Covered Court', '08:00:00', NOW()),
('Environmental Awareness Seminar', 'Learn about sustainable practices and environmental conservation.', '2026-05-25', 'Community Center', '14:00:00', NOW());

-- Insert sample polls
INSERT INTO public.polls (question, options, votes, total_votes, created_at, end_date) VALUES
('What type of community events would you like to see more of?',
'["Sports events", "Educational workshops", "Cultural activities", "Environmental initiatives"]',
'{"Sports events": 15, "Educational workshops": 22, "Cultural activities": 8, "Environmental initiatives": 12}',
57,
NOW() - INTERVAL '3 days',
NOW() + INTERVAL '7 days');

-- Insert sample volunteer opportunities
INSERT INTO public.volunteer_opportunities (title, description, date, location, required_skills, created_at) VALUES
('Community Clean-up Coordinator', 'Lead a team in organizing and executing the monthly clean-up drive.', '2026-05-18', 'Barangay Plaza', 'Leadership, Organization', NOW()),
('Youth Mentor Program', 'Mentor younger community members in various skills and activities.', '2026-05-22', 'Community Center', 'Teaching, Patience', NOW());

-- Insert sample volunteer signups (approved)
INSERT INTO public.volunteer_signups (opportunity_id, full_name, contact, email, status, created_at) VALUES
(1, 'Juan Dela Cruz', '+639123456789', 'juan@example.com', 'Approved', NOW() - INTERVAL '5 days'),
(1, 'Maria Santos', '+639987654321', 'maria@example.com', 'Approved', NOW() - INTERVAL '4 days'),
(2, 'Pedro Reyes', '+639555123456', 'pedro@example.com', 'Approved', NOW() - INTERVAL '3 days');

-- Insert sample user (for testing - adjust as needed)
-- Note: This assumes you have a user with ID 1. Adjust the ID if needed.
INSERT INTO public.sk_users (username, email, full_name, position, created_at) VALUES
('testuser', 'test@example.com', 'Test User', 'Youth Leader', NOW())
ON CONFLICT (id) DO NOTHING;

-- Insert sample event registrations
INSERT INTO public.event_registrations (event_id, user_id, registered_at) VALUES
(1, 1, NOW() - INTERVAL '2 days'),
(2, 1, NOW() - INTERVAL '1 day');

-- Insert sample feedback/suggestions
INSERT INTO public.suggestions (user_id, content, status, created_at) VALUES
(1, 'Great platform! Would love to see more virtual events.', 'approved', NOW() - INTERVAL '3 days'),
(1, 'Please add more sports facilities information.', 'pending', NOW() - INTERVAL '1 day');