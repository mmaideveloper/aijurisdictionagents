ALTER TABLE mcp_oauth_authorization_codes
ADD COLUMN IF NOT EXISTS scope TEXT NOT NULL DEFAULT 'mcp:laws';
