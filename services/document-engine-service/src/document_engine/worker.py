import logging
import signal
import time

from document_engine.config import settings
from document_engine.db import SessionLocal, init_db
from document_engine.processor import process_document_request
from document_engine.repository import claim_next_requests, mark_error, mark_finished

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s correlation_id=%(correlation_id)s %(message)s",
)
logger = logging.getLogger("document_engine.worker")
running = True


def stop_worker(signum: int, frame: object) -> None:
    global running
    running = False


def run_once() -> int:
    processed = 0
    with SessionLocal() as session:
        requests = claim_next_requests(session, batch_size=settings.worker_batch_size)

    for request in requests:
        processed += 1
        extra = {"correlation_id": request.correlation_id}
        logger.info("processing document request id=%s", request.id, extra=extra)
        try:
            result = process_document_request(
                request_id=request.id,
                correlation_id=request.correlation_id,
                document_type=request.document_type,
                payload=request.payload,
            )
        except Exception as exc:
            with SessionLocal() as session:
                mark_error(session, request.id, str(exc))
            logger.exception("document request failed id=%s", request.id, extra=extra)
        else:
            with SessionLocal() as session:
                mark_finished(session, request.id, result)
            logger.info("document request finished id=%s", request.id, extra=extra)
    return processed


def main() -> None:
    signal.signal(signal.SIGTERM, stop_worker)
    signal.signal(signal.SIGINT, stop_worker)
    init_db()
    logger.info("worker started", extra={"correlation_id": "-"})
    while running:
        processed = run_once()
        if processed == 0:
            time.sleep(settings.worker_poll_interval_seconds)
    logger.info("worker stopped", extra={"correlation_id": "-"})


if __name__ == "__main__":
    main()
