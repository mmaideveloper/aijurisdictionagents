from __future__ import annotations

import argparse
import json
import logging

from .worker import run_document_processor


def main() -> int:
    parser = argparse.ArgumentParser(description='Process uploaded case documents into text/vector records.')
    parser.add_argument('--limit', type=int, default=20)
    args = parser.parse_args()
    logger = logging.getLogger("document-processor")
    try:
        results = run_document_processor(limit=args.limit)
    except Exception:
        logger.exception("[document-processor] worker failed")
        raise

    logger.info(json.dumps([result.__dict__ for result in results], indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
