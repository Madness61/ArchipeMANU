import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

import pytest

from .fixtures import ROOT_MARKER
from .safety import checked_artifact_path

PROJECT = Path(__file__).resolve().parent.parent
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH",str(PROJECT/".playwright-browsers"))


def pytest_configure(config):
    # Playwright clears its output directory; reject dangerous CLI overrides before fixtures run.
    try:
        checked_artifact_path(config.getoption("output"))
        for name in ("basetemp","xmlpath"):
            value = getattr(config.option,name,None)
            if value:
                checked_artifact_path(value)
    except ValueError as exc:
        raise pytest.UsageError(str(exc)) from exc


@pytest.fixture
def artifact_dir(request,pytestconfig):
    name = re.sub(r"[^a-zA-Z0-9_.-]","-",request.node.name)
    folder = Path(pytestconfig.getoption("output"))/"logs"/name
    folder.mkdir(parents=True,exist_ok=True)
    return folder


@pytest.fixture
def live_server(artifact_dir):
    with tempfile.TemporaryDirectory(prefix="archipemanu-browser-") as folder:
        root = Path(folder)
        (root/".browser-test-root").write_text(ROOT_MARKER,encoding="utf-8")
        env = {key:value for key,value in os.environ.items()
               if not key.startswith(("HUB_","AP_"))}
        env.update(PYTHONUTF8="1",PYTHONIOENCODING="utf-8")
        with (artifact_dir/"server.log").open("w",encoding="utf-8") as log:
            process = subprocess.Popen([sys.executable,"-u","-m","browser_tests.server","--root",str(root)],
                                       cwd=PROJECT,env=env,stdout=log,stderr=subprocess.STDOUT,
                                       creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=="win32" else 0)
            try:
                deadline = time.monotonic()+20
                ready = root/"ready.json"
                while not ready.exists():
                    if process.poll() is not None:
                        raise RuntimeError(f"Testserver beendet ({process.returncode}), siehe {artifact_dir/'server.log'}")
                    if time.monotonic() > deadline:
                        raise RuntimeError(f"Testserver nicht bereit, siehe {artifact_dir/'server.log'}")
                    time.sleep(.05)
                url = json.loads(ready.read_text(encoding="utf-8"))["url"]
                assert url.startswith("http://127.0.0.1:")

                def calls():
                    path = root/"generation_calls.jsonl"
                    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []

                yield SimpleNamespace(url=url,root=root,calls=calls)
            finally:
                if process.poll() is None:
                    if sys.platform == "win32":
                        subprocess.run(["taskkill","/PID",str(process.pid),"/T","/F"],
                                       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10,check=False)
                    else:
                        process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
                calls_file = root/"generation_calls.jsonl"
                if calls_file.exists():
                    (artifact_dir/"generator-input.jsonl").write_bytes(calls_file.read_bytes())


@pytest.fixture
def actors(new_context,live_server,artifact_dir):
    logs = []
    errors = []
    pages = {}
    for actor in ("alice","bob","admin"):
        context = new_context(base_url=live_server.url,locale="de-DE",viewport={"width":1365,"height":950},accept_downloads=True)
        # No test may navigate to the production server or another external service.
        context.route("**/*",lambda route: route.continue_() if route.request.url.startswith(live_server.url+"/") else route.abort())
        page = context.new_page()
        page.set_default_timeout(15000)
        page.on("dialog",lambda dialog:dialog.accept())
        page.on("console",lambda message,who=actor:logs.append(f"[{who}] console {message.type}: {message.text}"))
        page.on("pageerror",lambda error,who=actor:errors.append(f"[{who}] {error}"))
        page.on("requestfailed",lambda request,who=actor:logs.append(f"[{who}] failed {request.method} {request.url}: {request.failure}"))
        page.on("response",lambda response,who=actor:logs.append(f"[{who}] HTTP {response.status} {response.url}") if response.status>=400 else None)
        pages[actor] = page
    try:
        yield SimpleNamespace(**pages)
    finally:
        (artifact_dir/"browser.log").write_text("\n".join(logs+errors),encoding="utf-8")
    assert not errors,"Unhandled browser JavaScript errors:\n"+"\n".join(errors)
