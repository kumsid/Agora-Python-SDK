# Cross-platform setup and support

This guide covers **automated setup** (macOS and Windows), **Linux limitations**, **PyPI wheels vs source builds**, **Apple Silicon / Rosetta**, **tokens and errors**, **load-testing script**, and **publishing your fork to GitHub**.

---

## Quick start (recommended)

From the **repository root**:

| OS | Command |
|----|---------|
| **macOS / Linux** | `python3 scripts/setup_native_sdk.py` |
| **Windows (cmd)** | `python scripts\setup_native_sdk.py` |
| **Unix wrapper** | `./setup.sh` (if executable) |

Optional flags:

| Flag | Meaning |
|------|--------|
| `--force` | Re-download the native SDK zip even if `AgoraRtcKit.framework` or `agora_rtc_sdk.dll` already exist. |
| `--skip-venv` | Do not create `.venv`; build with the `python` you invoked. |
| `--skip-build` | Only download / place native libs (and create venv); skip `build_ext`. |

The script creates **`.venv`**, drops the correct **native libraries** in the repo root, then runs:

`python setup.py build_ext --inplace`

---

## Platform support matrix

| OS | Automated download + build in this repo | Notes |
|----|-------------------------------------------|--------|
| **macOS (Intel)** | Yes | Use Xcode / CLT; framework is x86_64 in the official v3.1.2 FULL zip. |
| **macOS (Apple Silicon)** | Yes | Native framework from the same zip is **Intel-only**. The setup script sets `ARCHFLAGS=-arch x86_64` for the extension. Run apps with **`arch -x86_64 .venv/bin/python ...`** so the interpreter matches the `.so`. |
| **Windows 64-bit** | Yes | Visual Studio Build Tools with C++; copies `agora_rtc_sdk.dll` / `.lib` from `x86_64` inside the zip. |
| **Linux** | **No** (by design of upstream `setup.py`) | `setup.py` only defines link rules for **Darwin** and **Windows**. The setup script prints an explanation and exits. Real Linux support would require new `Extension` flags and Agora’s Linux RTC `.so` layout. |

---

## Prerequisites

### macOS

- **Xcode** or **Xcode Command Line Tools** (`clang++`, frameworks).
- **Python 3.8+** recommended (3.11 is commonly used for local builds).
- **Network** access to `download.agora.io` for the first run (unless you place the framework manually).

### Windows

- **Python 3** on `PATH`.
- **Visual Studio 2017+** with **Desktop development with C++** (MSVC, Windows SDK).
- Same network requirement for the Windows SDK zip.

### Linux

- Use a **macOS or Windows** machine or VM to build this fork, or extend `setup.py` yourself for Linux.

---

## Manual setup (if you skip the script)

### macOS

1. Download [Agora Native SDK for Mac v3.1.2 FULL](https://download.agora.io/sdk/release/Agora_Native_SDK_for_Mac_v3_1_2_FULL.zip).
2. Copy **`AgoraRtcKit.framework`** from the zip’s `libs` folder into the **repo root** (same folder as `setup.py`).
3. `python3 -m venv .venv`
4. On **Apple Silicon**:  
   `ARCHFLAGS="-arch x86_64" .venv/bin/python setup.py build_ext --inplace`  
   On **Intel**:  
   `.venv/bin/python setup.py build_ext --inplace`

Note: the README typo “AograRtcEngineKit” should read **`AgoraRtcKit.framework`**.

### Windows

1. Download [Agora Native SDK for Windows v3.1.2 FULL](https://download.agora.io/sdk/release/Agora_Native_SDK_for_Windows_v3_1_2_FULL.zip).
2. From `libs/x86_64`, copy **`agora_rtc_sdk.dll`** and **`agora_rtc_sdk.lib`** to the repo root.
3. `python -m venv .venv`
4. `.venv\Scripts\python setup.py build_ext --inplace`

---

## PyPI (`pip install agora-python-sdk`) vs source build

- **PyPI** ships **cp36–cp39** wheels for macOS x86_64 and Windows amd64 only. **Python 3.10+** often has **no matching wheel**, so `pip install agora-python-sdk` can fail with “no matching distribution”.
- **Source build** (this repo) tracks your **installed Python version** but still depends on the **native** Mac framework or Windows DLLs.

---

## Agora Console: App ID, App Certificate, tokens

- **`ERR_INVALID_TOKEN` / `onError` … `110`**: usually **App Certificate enabled** but join uses an **empty** or **wrong** token. Tokens must match **channel**, **uid**, and **app certificate** when applicable.
- With certificate on, you typically need a **server-generated RTC token per uid** (or a documented token mode your project uses).
- For quick local tests only, some teams temporarily **disable App Certificate** in the console (not for production).

---

## Load testing script (`scripts/channel_load_clients.py`)

- Configure **`.env`** (copy from `.env.example`); never commit real secrets.
- Each “user” is a **separate OS process** with a full RTC engine — scale gradually.
- **CSV stats**: default directory `rtc_stats_logs/` (see `.env.example` for `RTC_STATS_CSV_DIR`).
- **Apple Silicon**: run with **`arch -x86_64`** if your extension is x86_64.

See comments at the top of `channel_load_clients.py` for env variables and warnings about large `CLIENT_COUNT`.

---

## Troubleshooting

| Symptom | Things to check |
|--------|-------------------|
| ImportError wrong architecture (arm64 vs x86_64) | Build and run under **Rosetta** on Apple Silicon, or use an Intel Mac. |
| `dlopen` / missing framework | Run from repo root; ensure `AgoraRtcKit.framework` sits next to `_agorartc*.so`. |
| Windows link errors | MSVC C++ workload installed; `.dll` and `.lib` in repo root. |
| 110 token errors | Certificate + token generation + uid/channel alignment. |
| Too many processes | Lower `CLIENT_COUNT`; stagger `JOIN_STAGGER_MS`. |

---

## Pushing this project to GitHub

These steps assume you want **your own copy** (fork or new repo), not necessarily write access to `AgoraIO-Community/Agora-Python-SDK`.

### 1. Do not commit secrets or huge artifacts

Keep **out of git** (already partially covered by `.gitignore`):

- `.env` (App ID, tokens)
- `.venv/`
- `AgoraRtcKit.framework/`, `agora_rtc_sdk.dll`, `agora_rtc_sdk.lib`
- `build/`, `*.so`, `*.pyd`, `rtc_stats_logs/`

If you committed secrets, **rotate** them in the Agora console.

### 2. Create an empty repository on GitHub

GitHub → **New repository** → choose name (e.g. `Agora-Python-SDK`) → create **without** README if you already have one locally (avoids merge conflicts).

### 3. Point `git` at your GitHub repo and push

From your local clone:

```bash
cd /path/to/Agora-Python-SDK

# Optional: see current remote
git remote -v

# If you still point at upstream only, add YOUR repo as origin (example URL)
git remote add myfork https://github.com/YOUR_USERNAME/YOUR_REPO.git

# Or replace origin (only if you intend to stop using upstream as default)
# git remote set-url origin https://github.com/YOUR_USERNAME/YOUR_REPO.git

git branch -M main
git push -u myfork main
```

Use **SSH** if you prefer:

`git remote add myfork git@github.com:YOUR_USERNAME/YOUR_REPO.git`

### 4. First-time authentication

- **HTTPS**: GitHub requires a **Personal Access Token** (PAT) instead of your account password for `git push`.
- **SSH**: add your public key in GitHub → **Settings → SSH and GPG keys**.

### 5. Optional: GitHub fork workflow

If you used GitHub’s **Fork** button on the upstream repo, clone **your fork**, add **upstream** for updates:

```bash
git remote add upstream https://github.com/AgoraIO-Community/Agora-Python-SDK.git
git fetch upstream
```

Push branches to **`origin`** (your fork).

---

## Related files

| Path | Role |
|------|------|
| `scripts/setup_native_sdk.py` | Cross-platform setup driver (macOS / Windows). |
| `setup.sh` / `setup.cmd` | Thin wrappers to run the driver from repo root. |
| `setup.py` | Native extension build (Darwin / Windows only in upstream). |
| `scripts/channel_load_clients.py` | Optional multi-process channel load / CSV stats. |
| `.env.example` | Template for load script (no secrets). |

For API usage, see the root **README.md** and Agora’s C++ API reference linked there.
