try:
    from prometheus_client import CONTENT_TYPE_LATEST, Gauge, generate_latest
except ImportError:
    Gauge = None; generate_latest = lambda: b""; CONTENT_TYPE_LATEST = "text/plain"
from fastapi import Response


def install_metrics(app, get_worker):
    gauge=Gauge("paper_equity","Current paper equity") if Gauge else None
    @app.get("/metrics")
    def metrics():
        worker=get_worker()
        if worker and gauge: gauge.set(worker.broker.equity({}))
        return Response(generate_latest(),media_type=CONTENT_TYPE_LATEST)
