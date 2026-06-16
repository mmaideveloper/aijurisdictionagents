ALTER TABLE mcp_oauth_authorization_codes
ADD COLUMN IF NOT EXISTS resource TEXT NOT NULL DEFAULT '';
