INSERT INTO law_provisions (
    provision_id, version_id, anchor, heading, body_text, ordinal, created_at
) VALUES (
    'issue-808-provision-1', 'issue-808-prompt-boundary-v1', '§ 1',
    'Predmet syntetickej úpravy',
    %s,
    1, %s
)
