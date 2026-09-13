"""Local synthetic task 804 E2E setup and service launcher; never targets production."""
import os
import sys
import json
import hashlib
import subprocess
from urllib.parse import quote
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT), str(ROOT / 'api/aijuristiction-api')]
load_dotenv(ROOT / '.env', override=False)
container = json.loads(subprocess.check_output(['docker', 'inspect', 'aijurisdiction-laws-collector-postgres-local']))[0]
settings = dict(item.split('=', 1) for item in container['Config']['Env'] if '=' in item)
os.environ['LAWS_DB_CLOUD'] = 'postgresql://postgres:' + quote(settings['POSTGRES_PASSWORD'], safe='') + '@127.0.0.1:5433/laws_review_800_upload804'
os.environ['LAWS_DB_BACKEND'] = 'postgres'
os.environ.update(DB_OPTION='postgres', DB_CLOUD='postgresql://postgres:postgres@127.0.0.1:5432/juris_chat_upload_804',
    LLM_PROVIDER='azurefoundry', SYSTEM_EMBEDDING_MODEL_OPTION='local', SYSTEM_EMBEDDING_MODEL='all-MiniLM-L6-v2',
    STORAGE_OPTION='local', STORE_LOCAL=str(ROOT/'runs/storage/chat-upload-804'), DOCUMENT_PROCESSOR_OPTION='api',
    INTERNAL_MCP_BASE_URL='http://127.0.0.1:8170', LOCAL_LLM_IO_LOGGING='false')
os.environ['INTERNAL_MCP_SHARED_SECRET'] = hashlib.sha256((os.environ['AI_MODEL_CREDENTIAL_ENCRYPTION_KEY']+'804').encode()).hexdigest()

if sys.argv[1] == 'seed':
    from aijurisdictionagents.api_db import ApiDatabaseStore
    store = ApiDatabaseStore.from_env()
    store.initialize()
    run_id = 'upload804-' + uuid4().hex[:10]
    user = store.create_user(email=run_id+'@example.test', password=os.environ['JURISDIGTA_E2E_TEST_USER_PASSWORD'],
        full_name='Synthetic Upload Tester', data_processing_consent_at=datetime.now(timezone.utc).isoformat(),
        data_processing_consent_version='synthetic-upload-804-v1')
    store.save_mfa_verification(user_id=user.user_id, purpose='global_login', expires_in_hours=1)
    store.save_mcp_otp_verification(user_id=user.user_id, purpose='web-login:upload804-device', expires_in_hours=1)
    store.upsert_ai_model_user_override(user_id=user.user_id, model_profile_id='azure_foundry_gpt_4o_mini',
        admin_user_id=user.user_id, reason='Synthetic task 804 local E2E')
    case = store.create_case(user_id=user.user_id, company_id=None, title='Synthetic chat document upload 804')
    out = ROOT/'runs/chat-upload-804'
    out.mkdir(parents=True, exist_ok=True)
    (out/'input.json').write_text(json.dumps(dict(runId=run_id, userId=user.user_id, email=user.email, caseId=case.case_id,
        syntheticOnly=True, database='juris_chat_upload_804')), encoding='utf-8')
    print('Synthetic task 804 case prepared; manifest contains no credentials.')
elif sys.argv[1] == 'test':
    os.environ.update(VITE_API_BASE_URL='http://127.0.0.1:8180', VITE_API_KEY='aijuris')
    raise SystemExit(subprocess.call(['npx.cmd', 'playwright', 'test', 'e2e/issue-804-chat-upload.spec.ts'], cwd=ROOT/'frontend/aijurisdictionfronend'))
elif sys.argv[1] == 'laws':
    from aijurisdictionagents.db_migrations import apply_sql_migrations
    apply_sql_migrations(project='laws', db_option='postgres', target=os.environ['LAWS_DB_CLOUD'], dry_run=False)
    from scripts.seed_document_review_e2e import main
    main()
else:
    import uvicorn
    uvicorn.run('app.mcp_main:app' if sys.argv[1]=='mcp' else 'app.main:app', host='127.0.0.1',
        port=8170 if sys.argv[1]=='mcp' else 8180)
