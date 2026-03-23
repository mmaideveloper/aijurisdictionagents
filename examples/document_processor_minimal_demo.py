from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from tempfile import mkdtemp

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from aijurisdictionagents.api_db import ApiDatabaseStore
from services.document_processor.worker import run_document_processor

temp_dir = mkdtemp(prefix="document-processor-demo-")
try:
    root = Path(temp_dir)
    os.environ['LLM_PROVIDER'] = 'mock'
    os.environ['DB_OPTION'] = 'local'
    os.environ['STORAGE_OPTION'] = 'local'
    os.environ['DB_LOCAL'] = str(root / 'api.sqlite3')
    os.environ['STORE_LOCAL'] = str(root / 'storage')

    store = ApiDatabaseStore.from_env()
    store.initialize()
    user = store.create_user(email='processor@example.com', password='secret', phone_number='+421900000777')
    case = store.create_case(user_id=user.user_id, company_id=None, title='Processor demo')
    store.add_case_document(
        case_id=case.case_id,
        kind='uploaded',
        version=1,
        original_filename='notes.txt',
        payload=b'Lease increase notice and payment deadline.',
        uploaded_by_user_id=user.user_id,
    )

    results = run_document_processor(limit=5)
    print(results)
    print(store.list_case_document_contents(case_id=case.case_id))
    print(store.list_case_document_chunks(case_id=case.case_id))
finally:
    shutil.rmtree(temp_dir, ignore_errors=True)
