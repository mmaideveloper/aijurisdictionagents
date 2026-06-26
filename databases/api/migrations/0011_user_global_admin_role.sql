ALTER TABLE users ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'user';
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_enabled INTEGER NOT NULL DEFAULT 1;

UPDATE users
SET role = 'admin', is_enabled = 1
WHERE lower(email) IN ('mmaideveloper@gmail.com');
