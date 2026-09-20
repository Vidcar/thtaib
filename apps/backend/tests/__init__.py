"""Isolate even the application's import-time instance before tests import it."""
import atexit
import os
from pathlib import Path
import shutil
import sys
import tempfile

_scratch = Path(__file__).resolve().parents[3] / ".scratch"
_scratch.mkdir(exist_ok=True)
_session = Path(tempfile.mkdtemp(prefix="backend-tests-", dir=_scratch)).resolve()
assert _session.parent == _scratch.resolve()
# Deliberately override inherited product settings: tests never open everyday data.
os.environ["WORKBENCH_DATA_ROOT"] = str(_session / "app")
os.environ["TEMP"] = os.environ["TMP"] = str(_session)
tempfile.tempdir = str(_session)


def _close_test_session() -> None:
    if not _session.exists():
        return
    module = sys.modules.get("workbench_backend.app")
    if module is not None and hasattr(module, "app"):
        from tests.support import close_workbench_sqlite
        close_workbench_sqlite(module.app)
    shutil.rmtree(_session)


atexit.register(_close_test_session)
