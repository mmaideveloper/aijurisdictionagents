-- Synthetic legal-reader fixture only; never a real law or production seed.
INSERT INTO law_documents(document_id,country_code,collection_code,law_year,law_number,
 official_name,lawyer_title,source_url,publication_date,current_status,first_effective_date,
 first_stored_at,last_stored_at,last_checked_at,last_download_status,last_download_error,
 download_attempt_count,created_at,updated_at)
VALUES (%(run)s,'SK','ZZ',2026,9998,'Syntetický predpis na overenie odkazov',
 'Syntetický predpis','https://static.slov-lex.sk/pravne-predpisy/SK/ZZ/2026/9998/',
 '2026-01-01','published','2026-01-01',now(),now(),now(),'stored','',1,now(),now());
INSERT INTO law_versions(version_id,document_id,version_token,effective_from,version_checksum,
 status,html_checksum,pdf_checksum,html_bytes,pdf_bytes,normalized_json,embedding_vector,
 stored_at,created_at,updated_at)
SELECT %(run)s || '-' || token,%(run)s,token,day::date,token,'published',token,'',0,0,'{}','[1,0,0,0,0,0,0,0]',now(),now(),now()
FROM (VALUES ('20260101','2026-01-01'),('20270101','2027-01-01')) AS versions(token,day);
INSERT INTO law_provisions(provision_id,version_id,anchor,heading,body_text,ordinal,created_at)
VALUES
 (%(run)s || '-1',%(run)s || '-20260101','paragraf-4.odsek-1.text','§ 4 ods. 1','Syntetický odsek bez zvýraznenia.',1,now()),
 (%(run)s || '-2',%(run)s || '-20260101','paragraf-4.odsek-2.pismeno-i.text','§ 4 ods. 2 písm. i)','Susedné písmeno i).',2,now()),
 (%(run)s || '-3',%(run)s || '-20260101','paragraf-4.odsek-2.pismeno-j.text','§ 4 ods. 2 písm. j)',
  'Syntetické ustanovenie pre rok 2026: overte totožnosť a skontrolujte všetky požadované doklady. Toto je testovací text, nie právny predpis.',3,now()),
 (%(run)s || '-4',%(run)s || '-20270101','paragraf-4.odsek-2.pismeno-j.text','Budúce znenie','FUTURE_VERSION_MUST_NOT_APPEAR',1,now());
