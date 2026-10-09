"""Offline schema example: python examples/flow_draft_validation_demo.py."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'api/aijuristiction-api'))

from pydantic import ValidationError

from app.flow_packs.models import FlowPackCreateVersionRequest

if __name__ == '__main__':
    try:
        FlowPackCreateVersionRequest(positive_examples=[])
    except ValidationError:
        print('Empty examples rejected without printing input or exception payload')
    request = FlowPackCreateVersionRequest(positive_examples=['Synthetic matching request'])
    assert len(request.positive_examples or []) == 1
    print('Explicit synthetic matching example accepted')
