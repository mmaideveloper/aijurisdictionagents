from __future__ import annotations

import argparse
import json

from .worker import run_document_processor


def main() -> int:
    parser = argparse.ArgumentParser(description='Process uploaded case documents into text/vector records.')
    parser.add_argument('--limit', type=int, default=20)
    args = parser.parse_args()
    results = run_document_processor(limit=args.limit)
    print(json.dumps([result.__dict__ for result in results], indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
