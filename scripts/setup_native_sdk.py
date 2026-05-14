#!/usr/bin/env python3
"""
Cross-platform development setup for Agora-Python-SDK (from source).

  - macOS: downloads the v3.1.2 Mac native SDK, places AgoraRtcKit.framework in the
    repo root, creates .venv, runs build_ext --inplace. On Apple Silicon, builds
    the extension as x86_64 to match the official Intel-only framework (use Rosetta
    to run Python, see docs).

  - Windows: downloads the v3.1.2 Windows native SDK, copies agora_rtc_sdk.dll and
    agora_rtc_sdk.lib (x86_64) to the repo root, creates .venv, builds in place.

  - Linux: downloads Agora's Linux RTC SDK zip from download.agora.io (unversioned
    "FULL" package; override with AGORA_LINUX_SDK_URL), copies the x86_64 or
    arm64-v8a .so set into the repo root, then builds like macOS/Windows. The CDN
    does not mirror Mac/Windows-style v3_1_2 Linux zips; native ABI may differ
    slightly from the pinned 3.1.2 bindings—report issues if symbols mismatch.

Usage (from repository root):

  python3 scripts/setup_native_sdk.py
  python3 scripts/setup_native_sdk.py --force        # re-download native libs
  python3 scripts/setup_native_sdk.py --skip-venv  # use current interpreter only

Windows (cmd):

  py -3 scripts\\setup_native_sdk.py
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

SDK_MAC_URL = "https://download.agora.io/sdk/release/Agora_Native_SDK_for_Mac_v3_1_2_FULL.zip"
SDK_WIN_URL = "https://download.agora.io/sdk/release/Agora_Native_SDK_for_Windows_v3_1_2_FULL.zip"
# Agora does not publish Linux v3_1_2 at the same versioned URL pattern as Mac/Windows; this FULL bundle is used.
SDK_LINUX_DEFAULT_URL = "https://download.agora.io/sdk/release/Agora_Native_SDK_for_Linux_FULL.zip"


def _log(msg: str) -> None:
    print(msg, flush=True)


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    _log(f"Downloading:\n  {url}\n  -> {dest}")
    with urllib.request.urlopen(url, timeout=600) as resp, open(dest, "wb") as out:
        shutil.copyfileobj(resp, out)


def _extract_zip(zip_path: Path, dest_dir: Path) -> None:
    # zipfile.extractall does not recreate macOS framework symlinks (writes link targets as
    # plain files), which breaks linking. ditto preserves symlinks when expanding zips.
    if platform.system() == "Darwin":
        subprocess.run(
            ["ditto", "-x", "-k", "--noqtn", str(zip_path), str(dest_dir)],
            check=True,
        )
        return
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest_dir)


def _find_under(root: Path, name: str) -> Path | None:
    for p in root.rglob(name):
        if p.is_file() or p.is_dir():
            return p
    return None


def _mac_framework_present() -> bool:
    fw = REPO_ROOT / "AgoraRtcKit.framework"
    return fw.is_dir() and (fw / "AgoraRtcKit").exists()


def _win_libs_present() -> bool:
    return (REPO_ROOT / "agora_rtc_sdk.dll").is_file() and (REPO_ROOT / "agora_rtc_sdk.lib").is_file()


def _linux_sdk_abi_dir() -> str:
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        return "x86_64"
    if machine in ("aarch64", "arm64"):
        return "arm64-v8a"
    raise SystemExit(
        f"Unsupported Linux machine {platform.machine()!r}; "
        "expected x86_64/amd64 or aarch64/arm64."
    )


def _linux_native_sdk_ready() -> bool:
    return (REPO_ROOT / "libagora_rtc_sdk.so").is_file()


def _remove_linux_native_libs() -> None:
    for p in REPO_ROOT.glob("libagora*.so"):
        if p.is_file():
            p.unlink()
    aosl = REPO_ROOT / "libaosl.so"
    if aosl.is_file():
        aosl.unlink()


def _setup_linux(force: bool) -> None:
    abi = _linux_sdk_abi_dir()
    if not force and _linux_native_sdk_ready():
        _log("Linux native libs already in repo root (--force to re-download).")
        return

    url = os.environ.get("AGORA_LINUX_SDK_URL", SDK_LINUX_DEFAULT_URL)
    if force or _linux_native_sdk_ready():
        _remove_linux_native_libs()

    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td)
        zpath = tdir / "sdk.zip"
        _download(url, zpath)
        extract_root = tdir / "extracted"
        extract_root.mkdir()
        _extract_zip(zpath, extract_root)
        libdirs = [
            p.parent
            for p in extract_root.rglob("libagora_rtc_sdk.so")
            if p.parent.name == abi and "__MACOSX" not in p.parts
        ]
        if not libdirs:
            raise SystemExit(
                f"Could not find rtc/sdk/{abi}/libagora_rtc_sdk.so in the Linux SDK archive.\n"
                f"URL: {url}"
            )
        src_dir = libdirs[0]
        n = 0
        for so in sorted(src_dir.glob("*.so")):
            if so.is_file():
                shutil.copy2(so, REPO_ROOT / so.name)
                n += 1
        if not n:
            raise SystemExit(f"No *.so files under {src_dir}")
    _log(f"Installed {n} shared libraries ({abi}) into repo root.")


def _setup_mac(force: bool) -> None:
    if not force and _mac_framework_present():
        _log("AgoraRtcKit.framework already in repo root (--force to re-download).")
        return

    if REPO_ROOT.joinpath("AgoraRtcKit.framework").exists():
        shutil.rmtree(REPO_ROOT / "AgoraRtcKit.framework", ignore_errors=True)

    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td)
        zpath = tdir / "sdk.zip"
        _download(SDK_MAC_URL, zpath)
        extract_root = tdir / "extracted"
        extract_root.mkdir()
        _extract_zip(zpath, extract_root)
        fw = _find_under(extract_root, "AgoraRtcKit.framework")
        if not fw or not fw.is_dir():
            raise SystemExit("Could not find AgoraRtcKit.framework inside the Mac SDK zip.")
        dest = REPO_ROOT / "AgoraRtcKit.framework"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(fw, dest)
    _log(f"Installed: {REPO_ROOT / 'AgoraRtcKit.framework'}")


def _setup_windows(force: bool) -> None:
    if not force and _win_libs_present():
        _log("agora_rtc_sdk.dll/.lib already in repo root (--force to re-download).")
        return

    for name in ("agora_rtc_sdk.dll", "agora_rtc_sdk.lib"):
        p = REPO_ROOT / name
        if p.exists():
            p.unlink()

    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td)
        zpath = tdir / "sdk.zip"
        _download(SDK_WIN_URL, zpath)
        extract_root = tdir / "extracted"
        extract_root.mkdir()
        _extract_zip(zpath, extract_root)
        candidates = list(extract_root.rglob("agora_rtc_sdk.dll"))
        if not candidates:
            raise SystemExit("Could not find agora_rtc_sdk.dll inside the Windows SDK zip.")
        pref = [p for p in candidates if "x86_64" in p.as_posix()]
        dll = pref[0] if pref else candidates[0]
        lib = dll.parent / "agora_rtc_sdk.lib"
        if not lib.is_file():
            raise SystemExit(f"Missing agora_rtc_sdk.lib next to dll at {dll.parent}")
        shutil.copy2(dll, REPO_ROOT / "agora_rtc_sdk.dll")
        shutil.copy2(lib, REPO_ROOT / "agora_rtc_sdk.lib")
    _log(f"Installed: {REPO_ROOT / 'agora_rtc_sdk.dll'} and .lib")


def _ensure_venv(skip_venv: bool) -> Path:
    """Return path to python executable to use for the build."""
    if skip_venv:
        return Path(sys.executable)
    vdir = REPO_ROOT / ".venv"
    py = vdir / ("Scripts" if platform.system() == "Windows" else "bin") / (
        "python.exe" if platform.system() == "Windows" else "python"
    )
    if not py.is_file():
        _log(f"Creating virtual environment: {vdir}")
        subprocess.run([sys.executable, "-m", "venv", str(vdir)], cwd=REPO_ROOT, check=True)
    if not py.is_file():
        raise SystemExit(f"venv python not found at {py}")
    pip = py.parent / ("pip.exe" if platform.system() == "Windows" else "pip")
    if pip.is_file():
        subprocess.run([str(py), "-m", "pip", "install", "-q", "-U", "pip"], cwd=REPO_ROOT, check=False)
    return py


def _build(py: Path) -> None:
    env = os.environ.copy()
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        # Official Mac v3.1.2 FULL zip ships x86_64 AgoraRtcKit only.
        env.setdefault("ARCHFLAGS", "-arch x86_64")
        _log("Apple Silicon: building extension as x86_64 (ARCHFLAGS=-arch x86_64). Run Python with Rosetta to load it.")

    _log(f"Building extension with: {py}")
    subprocess.run(
        [str(py), str(REPO_ROOT / "setup.py"), "build_ext", "--inplace"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
    )
    _log("Build finished.")


def _smoke_import(py: Path) -> None:
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        _log("Skipping import smoke test on arm64 (extension is x86_64); use: arch -x86_64 .venv/bin/python -c \"import agorartc\"")
        return
    r = subprocess.run(
        [str(py), "-c", "import agorartc; print('import agorartc: OK')"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        _log(r.stderr or r.stdout or "import failed")
        raise SystemExit("Smoke import failed.")
    _log(r.stdout.strip())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true", help="Re-download native SDK artifacts even if present.")
    ap.add_argument("--skip-venv", action="store_true", help="Do not create .venv; build with the current python.")
    ap.add_argument("--skip-build", action="store_true", help="Only fetch native libs / venv, do not compile.")
    args = ap.parse_args()

    os.chdir(REPO_ROOT)
    system = platform.system()

    if system == "Darwin":
        _setup_mac(args.force)
    elif system == "Windows":
        _setup_windows(args.force)
    elif system == "Linux":
        _setup_linux(args.force)
    else:
        _log(f"Unsupported OS: {system}")
        return 2

    py = _ensure_venv(args.skip_venv)
    if not args.skip_build:
        _build(py)
        try:
            _smoke_import(py)
        except SystemExit:
            raise
        except Exception as e:
            _log(f"Smoke test skipped: {e}")

    _log("Done.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as e:
        print(f"Command failed with exit code {e.returncode}", file=sys.stderr)
        raise SystemExit(e.returncode or 1)
