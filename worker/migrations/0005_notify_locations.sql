-- Add locations column to notify_subscriptions
ALTER TABLE notify_subscriptions ADD COLUMN locations TEXT NOT NULL DEFAULT '[]';
