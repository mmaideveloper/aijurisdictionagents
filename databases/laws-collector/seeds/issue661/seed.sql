-- Synthetic, isolated local acceptance database only. Never production legal data.
DELETE FROM law_documents WHERE document_id LIKE 'issue661-%%-law';
INSERT INTO law_documents (
 document_id,country_code,collection_code,law_year,law_number,official_name,lawyer_title,
 source_url,publication_date,current_status,first_effective_date,applicable_to,
 first_stored_at,last_stored_at,last_checked_at,last_download_status,last_download_error,
 download_attempt_count,created_at,updated_at
) VALUES (%(id)s,'SK','ZZ',2026,661,%(title)s,%(title)s,
 'https://static.slov-lex.sk/static/SK/ZZ/2026/661/20261016.html','2026-10-16',
 'published','2026-10-16','Synthetic agent-loop acceptance only',
 now(),now(),now(),'stored','',1,now(),now());
INSERT INTO law_versions (
 version_id,document_id,version_token,effective_from,version_checksum,status,
 html_checksum,pdf_checksum,html_bytes,pdf_bytes,normalized_json,embedding_vector,
 stored_at,created_at,updated_at,embedding_model,embedding_dimensions
) VALUES (%(version)s,%(id)s,'synthetic-v1','2026-10-16','synthetic661','active',
 'synthetic661','',256,0,'{"synthetic":true}','[0,0,0,0,0,0,0,0]',
 now(),now(),now(),'deterministic-legacy-8d',8);
INSERT INTO law_metadata (
 law_metadata_id,document_id,version_id,law_identifier_text,title,law_type,
 approval_date,publication_date,effective_from,author,issue_reference,legal_areas_json,
 metadata_json,created_at,updated_at
) VALUES (%(metadata)s,%(id)s,%(version)s,'661/2026 Z. z.',%(title)s,'zakon',
 '2026-10-16','2026-10-16','2026-10-16','Synthetic E2E',%(id)s,'["synthetic"]',
 '{"synthetic":true}',now(),now());
INSERT INTO source_artifacts (
 artifact_id,document_id,version_id,source_system,artifact_kind,source_url,checksum,
 content_text,content_blob,content_bytes,http_etag,http_last_modified,should_redownload,
 verification_status,download_error,fetched_at,last_checked_at
) VALUES (%(artifact)s,%(id)s,%(version)s,'synthetic-e2e','html',
 'https://static.slov-lex.sk/static/SK/ZZ/2026/661/20261016.html','synthetic661',
 %(text)s,NULL,256,'','',FALSE,'synthetic_verified','',now(),now());
