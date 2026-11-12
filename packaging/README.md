# Windows build (x64, Windows 10+)

The launcher does not start services automatically: **Запустить сервер** starts the control listener; **Подключить телефон безопасно** separately starts a temporary HTTPS pairing listener on the selected private-LAN adapter (8767). It opens the existing viewer only on request. Closing the launcher asks to terminate only the children it launched. No startup task, service, router forwarding or firewall rule is created by setup. DroidBridge keeps legacy runtime data at `%LOCALAPPDATA%/VzaimoPult` for compatibility (`VZAIMOPULT_DATA_DIR` override remains supported); uninstall preserves it deliberately.

Windows setup uses its own version **1.0.3**; the Android application currently uses **1.14**. These are independent component versions. Windows 1.0.3 offers an optional Android installation/download QR at startup and an Already installed shortcut to the separate pairing flow. The public download QR contains no pairing credentials. Startup display preference stays in local android_setup.json; the panel can be reopened. Existing Android APK installations remain compatible. Video/audio tools can be selected locally without editing PATH.

## Toolchain and repeatable recipe

Use Python 3.15 x64 with Tcl/Tk (tested host). Build requirements are pinned; this is a repeatable dependency recipe, **not a claim of bit-for-bit reproducible PE output**. Python itself, Windows SDK/runtime, wheel hashes, signing and timestamps also matter. Build manifest records source/payload SHA256 and installed dependency versions. Store the matching wheels if reproducing offline.

```powershell
python -m venv packaging/.venv-build
packaging/.venv-build/Scripts/python.exe -m pip install --only-binary=:all: -r packaging/requirements-build.txt
python -m unittest discover -s packaging -p test_packaging.py
python packaging/acquire_inno.py
packaging/.venv-build/Scripts/python.exe packaging/build_windows.py --output packaging/.build/droidbridge-release-01 --iscc packaging/.build-tools/inno-7.1.1/ISCC.exe
```

The default **slim setup excludes FFmpeg/ffplay** to avoid redistributing unreviewed static GPL binaries. Python, Tk, Pillow, QR and TLS dependencies are frozen: target users do not install Python. JPEG screenshots/control still work; H.264 and audio require separately downloaded `ffmpeg` + `ffplay`. The launcher lets the user select their extracted folder (or its `bin` subfolder); editing PATH is not required. Only after local confirmation are both selected programs probed with `-version` on a worker thread, each with a five-second timeout. Selection is stored in the local data directory; restart an already running server/viewer to apply it. An invalid saved selection does not silently fall back to another installation. The launcher provides an explicit official-site link, never an automatic download. For a local-only offline bundle add `--media-root X:/tools/ffmpeg-9.0.2-full_build`; its GPL release gate below still applies.

Inno Setup 7.1.1 is downloaded from the official GitHub release, SHA256-checked and unpacked with its supported `/PORTABLE=1`; no global installation. The downloaded compiler identifies itself as non-commercial-use only: obtain the appropriate Inno Setup license before using this build tool commercially (the compiler itself is not shipped to end users). The media root must already exist; the script never downloads ~436 MiB of FFmpeg binaries silently. `run_local_build.py` is a convenience probe using the approved installed FFmpeg from PATH. Use a fresh output for each build. Do not export `.build`, `.build-tools`, `.venv-build`, `__pycache__` as source.

The allowlist copies only explicitly named Python modules. Runtime token, custom apps, logs, PID files, keystores, diagnostics and other project files cannot enter staging via recursive copy. Tests seed sentinel private files, reject stale staging and reject escaping symlinks. PyInstaller freezes both components in one shared onedir launcher (`--component server` / `--component viewer`). Dynamic imports of source modules are bundled explicitly. No separate Python installation is needed on the target.

`--self-test OUTPUT_JSON` checks frozen Python/TLS/Pillow, imports both component entrypoints and pairing/apps panels without calling their main functions, binding sockets, starting server/viewer or touching real runtime data (temporary isolated data directory is removed). It is **not** a real phone/Windows installation integration test.

## Licensing and public release gate

The local Gyan **9.0.2 full build**, exact FFmpeg source commit **946fcce07b**, states **GPL v3**. `ffmpeg.exe` (~217.27 MiB) and `ffplay.exe` (~218.72 MiB) are separate executables in `media/`, not linked into the application. Full upstream LICENSE and README/configuration are copied to `licenses/`. Python/Pillow/cryptography/qrcode licenses are also collected. Neither application licensing nor a MIT project license overrides these components.

Sources:
- https://www.gyan.dev/ffmpeg/builds/
- https://github.com/FFmpeg/FFmpeg/commit/946fcce07b
- https://github.com/jrsoftware/issrc/releases/tag/is-7_1_1

**Do not publish the full offline setup until Corresponding Source for the static FFmpeg build, its linked dependencies and build scripts is hosted/provided in a GPLv3-compliant way (or an appropriate compliant source offer is arranged).** A source URL for FFmpeg alone is not sufficient to assert complete compliance for a static full build. The manifest deliberately says `public_release_ready: false`. The built installer may be used as a local build/test artifact; do not represent it as an audited redistribution-ready release. Code signing/SmartScreen trust is not supplied.

`audit_artifact.py --output packaging/.build/droidbridge-release-01` checks payload, installer hashes, current source equality and absence of known runtime file types. `integrity_ok: true` is **not** publication approval; `publish_allowed` separately requires the manifest release-validation gate and no bundled FFmpeg. Keep the default `public_release_ready: false` until install/uninstall and real pairing integration have been validated. Do not publish build logs or tool/venv folders; logs contain build-host paths.

Pairing protocol and production component behavior are parent-owned. If those modules change, rebuild from the final integrated source and rerun diagnostics; a previously frozen executable does not acquire changes automatically.
