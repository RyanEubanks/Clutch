"""Check this computer against Clutch's minimum and recommended requirements.

Run it from backend/ (the venv doesn't need to be active, but then the package check
uses whichever Python you ran it with):

    python check_setup.py

Only the standard library is used, so it works before `pip install`. Each line is
  [ok]  meets the recommendation
  [~~]  works, but below the recommendation (slower, or a feature is off)
  [!!]  below the minimum: Clutch won't run (or that feature won't work) until it's fixed
Exit code 1 if anything is below the minimum.
"""
import importlib.util
import json
import os
import platform
import re
import shutil
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parent

# Keep these in sync with the README's "System requirements" table.
PYTHON_MIN, PYTHON_REC = (3, 11), (3, 12)
NODE_MIN = ((20, 19), (22, 13))  # Vite 8 and ESLint 10: ^20.19 or >=22.13
NODE_REC = (24, 0)
OLLAMA_MIN = (0, 20)  # Gemma 4 needs a recent Ollama
RAM_MIN_GB, RAM_REC_GB = 8, 16
MODEL_GB = 7.2  # gemma4:e2b download
DISK_MIN_GB, DISK_REC_GB = 12, 20  # free space before Ollama and the model are installed
PACKAGES = {"flask": "Flask", "openai": "openai", "sympy": "SymPy", "dotenv": "python-dotenv",
            "werkzeug": "Werkzeug"}

problems, warnings = [], []


def line(status, label, detail=""):
    mark = {"ok": "[ok]", "warn": "[~~]", "fail": "[!!]"}[status]
    print(f"  {mark} {label:<22} {detail}")
    if status == "fail":
        problems.append(label)
    elif status == "warn":
        warnings.append(label)


def version_tuple(text):
    return tuple(int(n) for n in re.findall(r"\d+", text)[:3])


def read_env():
    """backend/.env as a dict (without needing python-dotenv)."""
    env = {}
    path = BACKEND / ".env"
    if path.exists():
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" in raw and not raw.lstrip().startswith("#"):
                key, _, value = raw.partition("=")
                env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def total_ram_gb():
    try:
        if sys.platform == "win32":
            import ctypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

            status = MemoryStatus()
            status.dwLength = ctypes.sizeof(MemoryStatus)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
            return status.ullTotalPhys / 1024**3
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024**3
    except (AttributeError, ValueError, OSError):
        return None


def get_json(url, timeout=3):
    with urllib.request.urlopen(url, timeout=timeout) as r:  # local Ollama only
        return json.loads(r.read().decode())


def check_python():
    v = sys.version_info[:3]
    text = ".".join(map(str, v))
    need = f"(minimum {PYTHON_MIN[0]}.{PYTHON_MIN[1]}, recommended {PYTHON_REC[0]}.{PYTHON_REC[1]}+)"
    if v[:2] < PYTHON_MIN:
        line("fail", f"Python {text}", f"too old {need}")
    elif v[:2] < PYTHON_REC:
        line("warn", f"Python {text}", f"works {need}")
    else:
        line("ok", f"Python {text}", need)
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    missing = [name for mod, name in PACKAGES.items() if importlib.util.find_spec(mod) is None]
    if missing:
        hint = "activate the venv, then: pip install -r requirements.txt"
        line("fail", "Python packages", f"missing {', '.join(missing)} ({hint})")
    else:
        line("ok", "Python packages", "Flask, openai, SymPy, python-dotenv"
             + ("" if in_venv else " (note: not running inside a venv)"))


def check_sqlite():
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
        fts = True
    except sqlite3.OperationalError:
        fts = False
    conn.close()
    version = sqlite3.sqlite_version
    if version_tuple(version) < (3, 24):
        line("fail", f"SQLite {version}", "too old (minimum 3.24, comes with Python 3.11+)")
    elif not fts:
        line("warn", f"SQLite {version}", "no full-text search (FTS5): textbook search will be slower")
    else:
        line("ok", f"SQLite {version}", "with full-text search (FTS5)")


def check_hardware():
    ram = total_ram_gb()
    if ram is None:
        line("warn", "Memory (RAM)", f"couldn't tell (minimum {RAM_MIN_GB} GB, recommended {RAM_REC_GB} GB)")
    else:
        # Machines sold as "8 GB" report a little less
        detail = f"{ram:.0f} GB (minimum {RAM_MIN_GB} GB, recommended {RAM_REC_GB} GB)"
        if ram < RAM_MIN_GB - 0.6:
            line("fail", "Memory (RAM)", detail + ": the model alone needs about 7 GB")
        elif ram < RAM_REC_GB - 0.6:
            line("warn", "Memory (RAM)", detail + ": close other apps while studying")
        else:
            line("ok", "Memory (RAM)", detail)
    free = shutil.disk_usage(BACKEND).free / 1024**3
    detail = f"{free:.0f} GB free (minimum {DISK_MIN_GB} GB, recommended {DISK_REC_GB} GB)"
    if free < 2:
        line("fail", "Disk space", detail)
    elif free < DISK_MIN_GB:
        line("warn", "Disk space", detail + f": enough only if the {MODEL_GB} GB model is already downloaded")
    elif free < DISK_REC_GB:
        line("warn", "Disk space", detail)
    else:
        line("ok", "Disk space", detail)
    machine = platform.machine().lower()
    if sys.platform == "darwin":
        mac = platform.mac_ver()[0]
        apple = machine in ("arm64", "aarch64")
        if mac and version_tuple(mac) < (14,):
            line("fail", f"macOS {mac}", "Ollama needs macOS 14 Sonoma or newer")
        elif not apple:
            line("warn", f"macOS {mac} (Intel)", "Ollama runs on the CPU only on Intel Macs: slow replies")
        else:
            line("ok", f"macOS {mac}", "Apple silicon (Ollama uses the GPU)")
    elif sys.platform == "win32":
        build = sys.getwindowsversion().build
        if build < 19045:
            line("fail", f"Windows build {build}", "Ollama needs Windows 10 22H2 (build 19045) or newer")
        else:
            line("ok", f"Windows build {build}", "an NVIDIA or AMD GPU makes replies much faster")
    else:
        line("ok", f"{platform.system()} {machine}", "an NVIDIA or AMD GPU makes replies much faster")


def check_ollama():
    env = read_env()
    if not env:
        line("fail", "backend/.env", "missing: copy .env.example to .env")
    base = env.get("MODEL_BASE_URL", "http://localhost:11434/v1")
    model = env.get("MODEL_NAME", "gemma4:e2b")
    root = re.sub(r"/v1/?$", "", base)
    try:
        version = get_json(f"{root}/api/version").get("version", "?")
    except (urllib.error.URLError, OSError, ValueError):
        line("fail", "Ollama", f"not reachable at {root}: install it from ollama.com and start it")
        return
    if version_tuple(version) and version_tuple(version) < OLLAMA_MIN:
        line("warn", f"Ollama {version}", f"older than {OLLAMA_MIN[0]}.{OLLAMA_MIN[1]} may not run Gemma 4: update it")
    else:
        line("ok", f"Ollama {version}", f"running at {root}")
    try:
        models = get_json(f"{root}/api/tags").get("models", [])
    except (urllib.error.URLError, OSError, ValueError):
        models = []
    names = {m.get("name"): m for m in models}
    found = names.get(model) or names.get(f"{model}:latest")
    if found:
        size = found.get("size", 0) / 1e9
        line("ok", f"Model {model}", f"downloaded ({size:.1f} GB)" if size else "downloaded")
    else:
        line("fail", f"Model {model}", f"not downloaded: ollama pull {model}")


def check_tools():
    node = shutil.which("node")
    if not node:
        line("fail", "Node.js", "not found: install Node.js 24 LTS from nodejs.org (needed for the frontend)")
    else:
        try:
            text = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=10).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            text = ""
        v = version_tuple(text)[:2]
        ok_min = bool(v) and ((v[0] == 20 and v >= NODE_MIN[0]) or (v[0] == 22 and v >= NODE_MIN[1]) or v[0] >= 23)
        need = "(minimum 20.19 or 22.13, recommended 24 LTS)"
        if not ok_min:
            line("fail", f"Node.js {text or '?'}", f"too old {need}")
        elif v < NODE_REC:
            line("warn", f"Node.js {text}", f"works {need}")
        else:
            line("ok", f"Node.js {text}", need)
    if shutil.which("git"):
        line("ok", "git", "for downloading free textbooks (optional)")
    else:
        line("warn", "git", "not found: only needed to download OpenStax textbooks")


def main():
    print("Clutch setup check\n")
    check_python()
    check_sqlite()
    check_hardware()
    check_ollama()
    check_tools()
    print()
    if problems:
        print(f"{len(problems)} problem(s) to fix before Clutch will run: {', '.join(problems)}.")
        return 1
    if warnings:
        print("Ready. Clutch will run; the [~~] lines are below the recommendation.")
    else:
        print("Ready. Everything meets the recommended requirements.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
