"""#4 residuals: overlapping jobs' logs, the worker's thread list, nested #job, the service
command's errors, and small wording."""
from __future__ import annotations

import logging
import threading
from pathlib import Path

import pytest

from fridgesheet import cli
from fridgesheet.web import actions

WEB = Path(__file__).resolve().parents[1] / "fridgesheet" / "web"


def test_two_overlapping_jobs_each_get_only_their_own_log_lines():
    """A stalled job keeps running while the next one starts; both forwarded every record
    from the `fridgesheet` loggers, so each transcript carried the other's lines, and the
    first to finish restored the log level under the second."""
    logger = logging.getLogger("fridgesheet.test.jobs")
    root = logging.getLogger("fridgesheet")
    before = root.level
    root.setLevel(logging.WARNING)
    a_lines, b_lines = [], []
    a_in, b_in, a_out = threading.Event(), threading.Event(), threading.Event()

    def job_a():
        with actions.forward_logs(a_lines.append):
            a_in.set(); b_in.wait()
            logger.info("from a")
        a_out.set()

    def job_b():
        a_in.wait()
        with actions.forward_logs(b_lines.append):
            b_in.set()
            logger.info("from b"); a_out.wait()
            logger.info("b after a finished")      # a's exit must not have silenced INFO
    ta, tb = threading.Thread(target=job_a), threading.Thread(target=job_b)
    ta.start(); tb.start(); ta.join(5); tb.join(5)
    try:
        assert a_lines == ["from a"]
        assert b_lines == ["from b", "b after a finished"]
        assert root.level == logging.WARNING           # restored once both are done
    finally:
        root.setLevel(before)


def test_the_worker_forgets_threads_that_have_ended():
    from fridgesheet.web import jobs
    w = jobs.Worker.__new__(jobs.Worker)
    dead = threading.Thread(target=lambda: None); dead.start(); dead.join()
    w._threads = [dead]
    w._loop = lambda: None
    w._start_thread()
    assert dead not in w._threads and len(w._threads) == 1


def test_no_page_wraps_the_job_card_in_a_second_id_job():
    """`_job.html` is `<div id="job">`; five pages wrapped it in another, so a page with a
    running job had two elements with one id and htmx swapped the inner one."""
    for name in ("dashboard.html", "settings.html", "reports.html", "diagnostics.html", "runs.html"):
        src = (WEB / "templates" / name).read_text(encoding="utf-8")
        assert '<div id="job">{% if job %}' not in src, name


def test_service_errors_other_than_service_error_are_a_message_not_a_traceback(monkeypatch, capsys):
    from fridgesheet.host import service
    monkeypatch.setattr(service, "install_service", lambda **kw: (_ for _ in ()).throw(FileNotFoundError("schtasks")))
    with pytest.raises(SystemExit) as e:
        cli.main(["service", "install"])
    assert e.value.code == 1 and "schtasks" in capsys.readouterr().err


def test_the_live_log_says_when_its_connection_drops_and_checks_again():
    js = (WEB / "static" / "app.js").read_text(encoding="utf-8")
    sse = js[js.index("function attachSse"):js.index("function attachSse") + 1400]
    onerror = sse[sse.index("es.onerror"):]
    assert "connection lost" in onerror and "htmx.ajax(\"GET\", pre.dataset.reload" in onerror


def test_a_long_source_state_in_the_header_is_cut_short():
    src = (WEB / "templates" / "_header.html").read_text(encoding="utf-8")
    assert "truncate(" in src


def test_an_empty_snapshot_does_not_blame_a_kid_filter_nobody_gave():
    from fridgesheet.reports import open_work
    from fridgesheet.reports.base import ReportError
    import inspect
    src = inspect.getsource(open_work.OpenWorkReport.build)
    assert "--kid None" not in src
    assert "no students" in src
