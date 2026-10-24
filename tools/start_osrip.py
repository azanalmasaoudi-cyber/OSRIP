"""One-click local startup for OSRIP on Windows.

Used by Visual Studio (F5 or the green Start button on the OSRIP.Launcher project), by
VS Code (the "OSRIP: start everything" task and launch configuration) and from a terminal:

    python tools\\start_osrip.py [--setup] [--no-browser] [--keep-db] [--check]

In order, stopping with an explanation at the first missing piece, it:
  1. checks the Python environment, Node.js, the frontend packages and PostgreSQL;
  2. starts the portable PostgreSQL dev cluster (backend/scripts/devdb.py) unless it is
     already running, creates the ``osrip_dev`` database if it is missing and applies
     forward-only migrations;
  3. starts the FastAPI backend and the Vite frontend, each only when no OSRIP instance
     already answers on its port (another program on a port moves OSRIP to a free port);
  4. opens the browser once the API reports ready and the frontend proxies to it.

Stop Debugging, closing the console window or Ctrl+C stops the backend and frontend this
launcher started: they run in a Windows job object that closes with this process, even
when it is killed. PostgreSQL is stopped gracefully if this launcher started it (a small
watchdog does it after a hard stop); --keep-db leaves it running.

Nothing is deleted or reset and nothing needs administrator rights. Standard library
only, so it runs before the backend's dependencies are installed and can say what is
missing. Any Python 3.11+ can run it; the backend itself runs in backend/.venv.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

IS_WINDOWS = os.name == "nt"
ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
VENV_PY = BACKEND / ".venv" / ("Scripts/python.exe" if IS_WINDOWS else "bin/python")
VITE_JS = FRONTEND / "node_modules" / "vite" / "bin" / "vite.js"


def _dev_home() -> Path:
    if os.environ.get("OSRIP_DEV_HOME"):
        return Path(os.environ["OSRIP_DEV_HOME"])
    if IS_WINDOWS:
        default = Path(os.environ["LOCALAPPDATA"]) / "OSRIP-dev"
        if (default / "pgdata").exists():
            return default
        # Same rule as backend/scripts/devdb.py: a cluster created from a packaged (MSIX)
        # app sits in that app's virtualised AppData; use it when it is the only one, so
        # existing data is found rather than a new, empty cluster created.
        found = sorted(
            Path(os.environ["LOCALAPPDATA"]).glob("Packages/*/LocalCache/Local/OSRIP-dev/pgdata")
        )
        if len(found) == 1:
            os.environ["OSRIP_DEV_HOME"] = str(found[0].parent)  # devdb.py and the API agree
            return found[0].parent
        return default
    return Path.home() / ".osrip-dev"


DEV_HOME = _dev_home()
PG_BIN = Path(os.environ.get("OSRIP_PG_BIN", DEV_HOME / "pgsql" / "bin"))
PG_DATA = DEV_HOME / "pgdata"
PG_PORT = int(os.environ.get("OSRIP_DEV_PG_PORT", "55432"))
PG_LOG = DEV_HOME / "postgres.log"
PWFILE = DEV_HOME / "superuser-password.txt"
STATE_FILE = DEV_HOME / "launcher.json"
LOG_DIR = DEV_HOME / "logs"
DB_NAME = "osrip_dev"
NODE_MIN = (22, 22)
API_PORT = int(os.environ.get("OSRIP_API_PORT", "8010"))
WEB_PORT = int(os.environ.get("OSRIP_WEB_PORT", "5173"))
READY_TIMEOUT = 120

# Windows process-creation flags and job-object constants.
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_BREAKAWAY_FROM_JOB = 0x01000000
CREATE_NO_WINDOW = 0x08000000
JOB_OBJECT_LIMIT_BREAKAWAY_OK = 0x00000800
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SYNCHRONIZE = 0x00100000
STILL_ACTIVE = 259

# Local calls never go through a system proxy.
_HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class Log:
    """Console (the Visual Studio / VS Code window) plus a file under the dev home."""

    def __init__(self, path: Path | None) -> None:
        self.lock = threading.Lock()
        self.file = None
        self.path = path
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            self.file = path.open("a", encoding="utf-8")
        with contextlib.suppress(AttributeError, ValueError):
            sys.stdout.reconfigure(errors="replace")  # consoles that cannot show Arabic

    def __call__(self, tag: str, message: str) -> None:
        line = f"{time.strftime('%H:%M:%S')} [{tag:>4}] {message}"
        with self.lock:
            print(line, flush=True)
            if self.file:
                self.file.write(line + "\n")
                self.file.flush()


@dataclass
class Problem:
    what: str
    fix: list[str] = field(default_factory=list)


class Stop(Exception):
    """A prerequisite or readiness failure, already explained to the user."""


# ---------------------------------------------------------------- Windows helpers


def _kernel32():  # noqa: ANN202
    import ctypes
    from ctypes import wintypes

    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenProcess.restype = wintypes.HANDLE
    k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    k.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    return k


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if not IS_WINDOWS:
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True
    import ctypes
    from ctypes import wintypes

    k = _kernel32()
    handle = k.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        code = wintypes.DWORD()
        return bool(k.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == STILL_ACTIVE
    finally:
        k.CloseHandle(handle)


def wait_for_pid(pid: int) -> None:
    """Block until the process exits (used by the watchdog)."""
    if not IS_WINDOWS:
        while pid_alive(pid):
            time.sleep(1)
        return
    k = _kernel32()
    handle = k.OpenProcess(SYNCHRONIZE, False, pid)
    if not handle:
        return
    try:
        k.WaitForSingleObject(handle, 0xFFFFFFFF)
    finally:
        k.CloseHandle(handle)


class KillOnCloseJob:
    """A job object holding this launcher and everything it starts. When the launcher
    ends for any reason (Stop Debugging kills it outright) Windows closes the handle and
    terminates the backend and frontend with it. PostgreSQL breaks away on purpose so it
    can be stopped gracefully instead of killed."""

    def __init__(self, log: Log) -> None:
        self.handle = None
        self.contains_self = False
        if not IS_WINDOWS:
            return
        import ctypes
        from ctypes import wintypes

        class IoCounters(ctypes.Structure):
            _fields_ = [
                (name, ctypes.c_ulonglong)
                for name in ("r_ops", "w_ops", "o_ops", "r_bytes", "w_bytes", "o_bytes")
            ]

        class BasicLimits(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BasicLimits),
                ("IoInfo", IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        k = _kernel32()
        k.CreateJobObjectW.restype = wintypes.HANDLE
        k.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        k.GetCurrentProcess.restype = wintypes.HANDLE
        k.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        k.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        handle = k.CreateJobObjectW(None, None)
        if not handle:
            log("run", "Could not create a job object; children are stopped on normal exit only.")
            return
        info = ExtendedLimits()
        info.BasicLimitInformation.LimitFlags = (
            JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | JOB_OBJECT_LIMIT_BREAKAWAY_OK
        )
        k.SetInformationJobObject(
            handle, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION, ctypes.byref(info), ctypes.sizeof(info)
        )
        self.handle = handle
        # Every child created from now on inherits the job, so none can slip out before
        # being assigned. Nested jobs need Windows 8 or later.
        self.contains_self = bool(k.AssignProcessToJobObject(handle, k.GetCurrentProcess()))
        self._k = k

    def adopt(self, proc: subprocess.Popen[str]) -> None:
        """Fallback when the launcher itself could not join the job."""
        if self.handle and not self.contains_self:
            self._k.AssignProcessToJobObject(self.handle, int(proc._handle))  # type: ignore[attr-defined]


def detached_popen(args: list[str], **kwargs) -> tuple[subprocess.Popen[bytes], bool]:  # noqa: ANN003
    """Start a process outside the launcher's job (PostgreSQL, the watchdog). Falls back to
    an ordinary child when an enclosing job forbids breakaway; the flag says which."""
    if IS_WINDOWS:
        with contextlib.suppress(OSError):
            return subprocess.Popen(
                args, creationflags=CREATE_NO_WINDOW | CREATE_BREAKAWAY_FROM_JOB, **kwargs
            ), True
        return subprocess.Popen(args, creationflags=CREATE_NO_WINDOW, **kwargs), False
    return subprocess.Popen(args, start_new_session=True, **kwargs), True


# ---------------------------------------------------------------- probes


def port_open(port: int) -> bool:
    """Something accepts connections on localhost:port (IPv4 or IPv6)."""
    for family, host in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
        with contextlib.suppress(OSError), socket.socket(family, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            if s.connect_ex((host, port)) == 0:
                return True
    return False


def http_get(url: str, timeout: float = 2.0) -> tuple[int | None, str]:
    try:
        with _HTTP.open(url, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")
    except (OSError, ValueError):
        return None, ""


def osrip_ready_body(base: str) -> dict | None:
    """The API's /health/ready answer when ``base`` is an OSRIP API (ready or not)."""
    _, text = http_get(f"{base}/api/v1/health/ready")
    with contextlib.suppress(ValueError):
        body = json.loads(text)
        if isinstance(body, dict) and "release" in body and "checks" in body:
            return body
    return None


def is_osrip_web(port: int) -> bool:
    status, text = http_get(f"http://localhost:{port}/")
    return (
        status == 200
        and "<title>OSRIP" in text
        and osrip_ready_body(f"http://localhost:{port}") is not None
    )


def free_port(start: int, avoid: set[int]) -> int:
    for port in range(start + 1, start + 40):
        if port not in avoid and not port_open(port):
            return port
    raise Stop(f"No free port found near {start}.")


def run(args: list[str], **kwargs) -> subprocess.CompletedProcess[str]:  # noqa: ANN003
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        **kwargs,
    )


# ---------------------------------------------------------------- prerequisites


def exe(name: str) -> Path:
    return PG_BIN / (f"{name}.exe" if IS_WINDOWS else name)


def find_node() -> Path | None:
    candidates: list[Path] = []
    if os.environ.get("OSRIP_NODE"):
        candidates.append(Path(os.environ["OSRIP_NODE"]))
    if found := shutil.which("node"):
        candidates.append(Path(found))
    if IS_WINDOWS:
        program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        candidates.append(program_files / "nodejs" / "node.exe")
        # Visual Studio's "Node.js development" workload ships its own copy.
        candidates += sorted(
            program_files.glob(
                "Microsoft Visual Studio/*/*/MSBuild/Microsoft/VisualStudio/NodeJs/node.exe"
            ),
            reverse=True,
        )
    for path in candidates:
        if path.is_file() and node_version(path) >= NODE_MIN:
            return path
    return None


def node_version(path: Path) -> tuple[int, int]:
    result = run([str(path), "--version"])
    match = re.match(r"v(\d+)\.(\d+)", result.stdout.strip())
    return (int(match[1]), int(match[2])) if match else (0, 0)


def check_prerequisites(log: Log, uses_dev_db: bool) -> Path:
    problems: list[Problem] = []
    if sys.version_info < (3, 11):
        problems.append(
            Problem(
                f"This launcher needs Python 3.11 or later (running {sys.version.split()[0]}).",
                [
                    "Select a Python 3.11+ environment in Visual Studio (Python Environments window)."
                ],
            )
        )
    if not VENV_PY.is_file():
        problems.append(
            Problem(
                "The backend virtual environment is missing (backend\\.venv).",
                [
                    f'cd "{BACKEND}"',
                    "py -3.13 -m venv .venv",
                    r".\.venv\Scripts\python.exe -m pip install -r requirements.lock",
                    r".\.venv\Scripts\python.exe -m pip install --no-deps -e .",
                ],
            )
        )
    else:
        probe = run([str(VENV_PY), "-c", "import fastapi, uvicorn, sqlalchemy, psycopg, alembic"])
        if probe.returncode != 0:
            problems.append(
                Problem(
                    "The backend packages are not installed in backend\\.venv.",
                    [
                        f'cd "{BACKEND}"',
                        r".\.venv\Scripts\python.exe -m pip install -r requirements.lock",
                        r".\.venv\Scripts\python.exe -m pip install --no-deps -e .",
                    ],
                )
            )
    node = find_node()
    if node is None:
        problems.append(
            Problem(
                f"Node.js {NODE_MIN[0]}.{NODE_MIN[1]} or later was not found.",
                [
                    "Install Node.js LTS from https://nodejs.org/ (or the Visual Studio 'Node.js development' workload),",
                    "or set OSRIP_NODE to the full path of node.exe.",
                ],
            )
        )
    if not VITE_JS.is_file():
        problems.append(
            Problem(
                "The frontend packages are not installed (frontend\\node_modules).",
                [f'cd "{FRONTEND}"', "npm ci"],
            )
        )
    if uses_dev_db and not exe("pg_ctl").is_file():
        problems.append(
            Problem(
                f"PostgreSQL binaries were not found in {PG_BIN}.",
                [
                    "Download the PostgreSQL 17 'Windows x86-64' binaries zip from",
                    "https://www.enterprisedb.com/download-postgresql-binaries and extract its pgsql folder to",
                    f"{DEV_HOME}  (no installer, service or administrator rights needed),",
                    "or set OSRIP_PG_BIN to an existing PostgreSQL bin folder.",
                ],
            )
        )
    if problems:
        log("chk", "OSRIP cannot start yet. Missing prerequisites:")
        for n, p in enumerate(problems, 1):
            log("chk", f"  {n}. {p.what}")
            for line in p.fix:
                log("chk", f"       {line}")
        raise Stop("prerequisites")
    log("chk", f"Python {sys.version.split()[0]} (launcher), backend venv {VENV_PY}")
    log("chk", f"Node.js {'.'.join(map(str, node_version(node)))} at {node}")  # type: ignore[arg-type]
    return node  # type: ignore[return-value]


# ---------------------------------------------------------------- database


def pg_env() -> dict[str, str]:
    return {**os.environ, "PGPASSWORD": PWFILE.read_text(encoding="utf-8").strip()}


def admin_url(database: str) -> str:
    password = PWFILE.read_text(encoding="utf-8").strip()
    return f"postgresql+psycopg://postgres:{password}@localhost:{PG_PORT}/{database}"


def pg_running() -> bool:
    return run([str(exe("pg_ctl")), "-D", str(PG_DATA), "status"]).returncode == 0


def pg_accepting() -> bool:
    return (
        run([str(exe("pg_isready")), "-h", "localhost", "-p", str(PG_PORT), "-q"]).returncode == 0
    )


def ensure_database(log: Log, state: dict) -> bool:
    """Start the dev cluster if needed; returns True when the database was just created."""
    if not PG_DATA.exists():
        log(
            "db",
            f"No dev cluster yet: initialising a new one in {PG_DATA} (nothing existing is touched).",
        )
        result = run([str(VENV_PY), str(BACKEND / "scripts" / "devdb.py"), "init"], cwd=BACKEND)
        for line in (result.stdout + result.stderr).splitlines()[-5:]:
            log("db", line)
        if result.returncode != 0:
            raise Stop("PostgreSQL initialisation failed; see the lines above.")
    if pg_running():
        log("db", f"PostgreSQL already running on port {PG_PORT} (left running on exit).")
    else:
        if port_open(PG_PORT):
            log(
                "db",
                f"Port {PG_PORT} is used by another program, so the OSRIP dev cluster cannot start.",
            )
            log(
                "db",
                "Close that program, or set OSRIP_DEV_PG_PORT and the port in "
                f"{PG_DATA / 'postgresql.conf'} to a free port.",
            )
            raise Stop("database port in use")
        log("db", f"Starting PostgreSQL (port {PG_PORT}, log {PG_LOG})...")
        proc, outside_job = detached_popen(
            [str(exe("pg_ctl")), "-D", str(PG_DATA), "-l", str(PG_LOG), "-w", "start"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if not outside_job:
            log(
                "db",
                "Note: the host keeps child processes in its own job, so a hard stop ends PostgreSQL "
                "abruptly (it recovers automatically on the next start).",
            )
        try:
            code = proc.wait(timeout=90)
        except subprocess.TimeoutExpired:
            code = -1
        if code != 0 or not pg_running():
            log("db", f"PostgreSQL did not start. Last lines of {PG_LOG}:")
            with contextlib.suppress(OSError):
                for line in PG_LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-8:]:
                    log("db", f"  {line}")
            raise Stop("database start failed")
        state["db_started_by"] = os.getpid()
        write_state(state)
    deadline = time.monotonic() + 30
    while not pg_accepting():
        if time.monotonic() > deadline:
            raise Stop("PostgreSQL is running but does not accept connections.")
        time.sleep(0.5)
    exists = run(
        [
            str(exe("psql")),
            "-h",
            "localhost",
            "-p",
            str(PG_PORT),
            "-U",
            "postgres",
            "-tAc",
            f"SELECT 1 FROM pg_database WHERE datname = '{DB_NAME}'",
        ],
        env=pg_env(),
    )
    if exists.returncode != 0:
        raise Stop(f"Could not query PostgreSQL: {exists.stderr.strip()}")
    if exists.stdout.strip() == "1":
        log("db", f"Database {DB_NAME} is available.")
        return False
    log("db", f"Creating database {DB_NAME} (first run)...")
    created = run(
        [str(exe("createdb")), "-h", "localhost", "-p", str(PG_PORT), "-U", "postgres", DB_NAME],
        env=pg_env(),
    )
    if created.returncode != 0:
        raise Stop(f"createdb failed: {created.stderr.strip()}")
    return True


def backend_step(log: Log, tag: str, args: list[str], env: dict[str, str]) -> None:
    result = run([str(VENV_PY), *args], cwd=BACKEND, env=env)
    for line in (result.stdout + result.stderr).splitlines():
        if line.strip():
            log(tag, line)
    if result.returncode != 0:
        raise Stop(f"'{' '.join(args)}' failed; see the lines above.")


def migrate_and_seed(log: Log, db_url: str, first_run: bool, setup: bool) -> None:
    env = {**os.environ, "OSRIP_DATABASE_URL": db_url}
    log("db", "Applying forward-only migrations (alembic upgrade head)...")
    backend_step(log, "db", ["-m", "alembic", "upgrade", "head"], env)
    if first_run or setup:
        log(
            "db",
            "Loading the labelled synthetic demo data and the curated reference pack (idempotent)...",
        )
        backend_step(log, "db", ["-m", "app.cli", "seed-synthetic"], env)
        backend_step(log, "db", ["-m", "app.cli", "import-reference-pack", "--publish"], env)


# ---------------------------------------------------------------- services


class Service:
    def __init__(
        self,
        tag: str,
        args: list[str],
        cwd: Path,
        env: dict[str, str],
        log: Log,
        job: KillOnCloseJob,
    ) -> None:
        self.tag = tag
        self.log = log
        self.tail: deque[str] = deque(maxlen=25)
        flags = CREATE_NEW_PROCESS_GROUP if IS_WINDOWS else 0
        self.proc = subprocess.Popen(
            args,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=flags,
        )
        job.adopt(self.proc)
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            line = re.sub(r"\x1b\[[0-9;]*m", "", line.rstrip())
            if line:
                self.tail.append(line)
                self.log(self.tag, line)

    def running(self) -> bool:
        return self.proc.poll() is None

    def stop(self) -> None:
        if not self.running():
            return
        with contextlib.suppress(OSError, ValueError):
            if IS_WINDOWS:
                self.proc.send_signal(signal.CTRL_BREAK_EVENT)  # graceful for uvicorn and Vite
            else:
                self.proc.terminate()
        try:
            self.proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=5)


def wait_until(
    check, what: str, service: Service | None, log: Log, timeout: int = READY_TIMEOUT
) -> None:  # noqa: ANN001
    deadline = time.monotonic() + timeout
    announced = time.monotonic()
    while True:
        if check():
            return
        if service is not None and not service.running():
            log("run", f"{what} exited before it was ready (exit code {service.proc.returncode}).")
            raise Stop(f"{what} failed to start")
        if time.monotonic() > deadline:
            raise Stop(f"{what} did not become ready within {timeout} s.")
        if time.monotonic() - announced > 10:
            log("run", f"Still waiting for {what}...")
            announced = time.monotonic()
        time.sleep(0.5)


# Optional services and the server-side settings (backend/.env) that switch them on.
INTEGRATION_HINTS = {
    "assistant": "AI answers: OSRIP_ANTHROPIC_API_KEY",
    "web_research": "web search: OSRIP_RESEARCH_API_KEY (Brave Search API)",
    "speech": "voice: OSRIP_SPEECH_KEY and OSRIP_SPEECH_REGION (Azure AI Speech)",
    "email": "e-mail: OSRIP_EMAIL_BACKEND=smtp and OSRIP_SMTP_*",
    "google": "Google sign-in: OSRIP_GOOGLE_CLIENT_ID/SECRET",
    "microsoft": "Microsoft sign-in: OSRIP_MICROSOFT_CLIENT_ID/SECRET",
}


def report_integrations(log: Log, body: dict) -> None:
    """Say which optional services are off, as reported by the API itself."""
    integrations = body.get("integrations") or {}
    missing = [
        hint
        for name, hint in INTEGRATION_HINTS.items()
        if (integrations.get(name) or {}).get("configured") is False
    ]
    if missing:
        log("api", "Not configured (the site works; these features say so on screen):")
        for hint in missing:
            log("api", f"  - {hint}")
        log("api", f"  Put the settings in {BACKEND / '.env'} (see backend/.env.example).")


# ---------------------------------------------------------------- state and watchdog


def read_state() -> dict:
    with contextlib.suppress(OSError, ValueError):
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def write_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def clear_state(pid: int) -> None:
    if read_state().get("pid") == pid:
        with contextlib.suppress(OSError):
            STATE_FILE.unlink()


def watchdog(launcher_pid: int) -> None:
    """Runs detached. After a hard stop of the launcher (Stop Debugging), stops PostgreSQL
    gracefully if that launcher started it and nothing else took over."""
    wait_for_pid(launcher_pid)
    state = read_state()
    if state.get("pid") == launcher_pid and state.get("db_started_by") == launcher_pid:
        run([str(exe("pg_ctl")), "-D", str(PG_DATA), "-m", "fast", "-w", "stop"])
        clear_state(launcher_pid)


def stop_database(log: Log) -> None:
    log("db", "Stopping PostgreSQL (started by this launcher)...")
    result = run([str(exe("pg_ctl")), "-D", str(PG_DATA), "-m", "fast", "-w", "stop"])
    log(
        "db",
        "PostgreSQL stopped."
        if result.returncode == 0
        else f"pg_ctl stop: {result.stderr.strip()}",
    )


# ---------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Start OSRIP locally (database, API, frontend, browser)."
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="also (re)load the synthetic demo data and the reference pack; both are idempotent",
    )
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser")
    parser.add_argument("--keep-db", action="store_true", help="leave PostgreSQL running on exit")
    parser.add_argument(
        "--with-sync-worker",
        action="store_true",
        help="also run the official-statistics sync worker (or set OSRIP_SYNC_WORKER=1); feeds "
        "are checked only after an administrator switches their schedule on",
    )
    parser.add_argument(
        "--check", action="store_true", help="only check prerequisites and ports, then exit"
    )
    parser.add_argument("--watchdog", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.watchdog:
        watchdog(args.watchdog)
        return 0

    log_path = None if args.check else LOG_DIR / f"launcher-{time.strftime('%Y%m%d-%H%M%S')}.log"
    log = Log(log_path)
    log("run", f"OSRIP launcher - project {ROOT}")
    if log_path:
        log("run", f"Log file: {log_path}")
    external_db = os.environ.get("OSRIP_DATABASE_URL")
    if not external_db:
        log("db", f"Development data folder: {DEV_HOME}")

    previous = read_state()
    alive = previous.get("pid") and previous["pid"] != os.getpid() and pid_alive(previous["pid"])
    # A stale file (crashed launcher, reused PID) is ignored unless its frontend still answers as OSRIP.
    if (
        alive
        and not args.check
        and "<title>OSRIP" in http_get(previous.get("web_url") or "http://invalid/")[1]
    ):
        log(
            "run",
            f"OSRIP is already running from another launcher (PID {previous['pid']}): {previous.get('web_url')}",
        )
        log(
            "run",
            "Stop that one first (close its window or Stop Debugging) to restart. Opening the browser.",
        )
        if not args.no_browser and previous.get("web_url"):
            webbrowser.open(previous["web_url"])
        return 0

    services: list[Service] = []
    state: dict = {"pid": os.getpid(), "started": time.strftime("%Y-%m-%dT%H:%M:%S")}
    job = KillOnCloseJob(log)
    try:
        node = check_prerequisites(log, uses_dev_db=not external_db)

        # Ports: reuse a running OSRIP, move away from anything else.
        api_port, web_port = API_PORT, WEB_PORT
        reuse_api = reuse_web = False
        if port_open(api_port):
            if osrip_ready_body(f"http://127.0.0.1:{api_port}"):
                reuse_api = True
                log(
                    "api",
                    f"An OSRIP API is already running on port {api_port}; using it (it will not be stopped).",
                )
            else:
                moved = free_port(api_port, {web_port})
                log(
                    "api",
                    f"Port {api_port} is used by another program; the API will use port {moved}.",
                )
                api_port = moved
        if port_open(web_port):
            if reuse_api and is_osrip_web(web_port):
                reuse_web = True
                log("web", f"The OSRIP frontend is already running on port {web_port}; using it.")
            else:
                moved = free_port(web_port, {api_port})
                log("web", f"Port {web_port} is in use; the frontend will use port {moved}.")
                web_port = moved
        api_base = f"http://127.0.0.1:{api_port}"
        web_url = f"http://localhost:{web_port}/"
        if args.check:
            log(
                "chk",
                f"Prerequisites OK. API port {api_port}{' (reuse)' if reuse_api else ''}, "
                f"web port {web_port}{' (reuse)' if reuse_web else ''}.",
            )
            if not external_db:
                log(
                    "chk",
                    f"PostgreSQL {'running' if PG_DATA.exists() and pg_running() else 'not running'} "
                    f"(data {PG_DATA}).",
                )
            return 0
        state.update(api_url=api_base, web_url=web_url)
        write_state(state)

        # Database.
        if not reuse_api:
            if external_db:
                log(
                    "db",
                    "OSRIP_DATABASE_URL is set: using that database as is (not started or migrated here).",
                )
            else:
                first_run = ensure_database(log, state)
                if state.get("db_started_by") == os.getpid() and not args.keep_db:
                    # Stops PostgreSQL gracefully if this process is killed (Stop Debugging).
                    detached_popen(
                        [
                            sys.executable,
                            str(Path(__file__).resolve()),
                            "--watchdog",
                            str(os.getpid()),
                        ],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                migrate_and_seed(log, admin_url(DB_NAME), first_run, args.setup)

            # Backend.
            env = {**os.environ, "PORT": str(api_port), "PYTHONUNBUFFERED": "1"}
            log("api", f"Starting the FastAPI backend on {api_base} ...")
            api = Service(
                "api",
                [str(VENV_PY), str(BACKEND / "scripts" / "serve_dev.py")],
                BACKEND,
                env,
                log,
                job,
            )
            services.append(api)
            try:
                wait_until(
                    lambda: (osrip_ready_body(api_base) or {}).get("ready") is True,
                    "the API",
                    api,
                    log,
                )
            except Stop:
                body = osrip_ready_body(api_base)
                if body is not None:  # answering but not ready: say which check fails
                    log(
                        "api", f"The API answers but is not ready: {json.dumps(body.get('checks'))}"
                    )
                raise
            body = osrip_ready_body(api_base) or {}
            log(
                "api",
                f"API ready: release {body.get('release')}, migration {body.get('checks', {}).get('migration')}.",
            )
            report_integrations(log, body)

            # The official-statistics sync worker: a process of its own, never the web server.
            if args.with_sync_worker or os.environ.get("OSRIP_SYNC_WORKER") == "1":
                log("sync", "Starting the official-statistics sync worker ...")
                services.append(
                    Service(
                        "sync",
                        [str(VENV_PY), str(BACKEND / "scripts" / "sync_worker_dev.py")],
                        BACKEND,
                        {**os.environ, "PYTHONUNBUFFERED": "1"},
                        log,
                        job,
                    )
                )

        # Frontend.
        if not reuse_web:
            env = {k: v for k, v in os.environ.items() if k != "PORT"}
            env.update(
                OSRIP_API_ORIGIN=api_base,
                OSRIP_WEB_PORT=str(web_port),
                NO_COLOR="1",
                FORCE_COLOR="0",
            )
            log("web", f"Starting the Vite frontend on {web_url} ...")
            web = Service("web", [str(node), str(VITE_JS)], FRONTEND, env, log, job)
            services.append(web)
            wait_until(lambda: is_osrip_web(web_port), "the frontend", web, log)
        log("run", f"OSRIP is ready: {web_url}  (API {api_base}/api/v1)")

        if not args.no_browser and not os.environ.get("OSRIP_NO_BROWSER"):
            webbrowser.open(web_url)
        if not services:
            log("run", "Nothing was started by this launcher, so there is nothing to keep running.")
            return 0
        log(
            "run",
            "Press Ctrl+C, close this window or use Stop Debugging to stop the services started here.",
        )
        while all(s.running() for s in services):
            time.sleep(1)
        failed = next(s for s in services if not s.running())
        log(
            "run",
            f"The {failed.tag} process stopped unexpectedly (exit code {failed.proc.returncode}); "
            "stopping the rest.",
        )
        return 1
    except Stop as stop:
        if str(stop) != "prerequisites":
            log("run", f"Startup stopped: {stop}")
        for service in services:
            if service.tail and not service.running():
                log("run", f"Last output of {service.tag}:")
                for line in service.tail:
                    log("run", f"  {line}")
        return 1
    except KeyboardInterrupt:
        log("run", "Stopping...")
        return 0
    finally:
        for service in reversed(services):
            service.stop()
            log(service.tag, "stopped.")
        if state.get("db_started_by") == os.getpid() and not args.keep_db:
            stop_database(log)
            state["db_started_by"] = None
        clear_state(os.getpid())


if __name__ == "__main__":
    sys.exit(main())
