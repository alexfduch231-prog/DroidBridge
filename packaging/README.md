# Windows build (x64, Windows 10+)

Windows setup version is **1.0.7**; Android's independent target remains **1.16 (versionCode 26)**. The positive staging allowlist contains **27 code modules plus one icon asset (28 files)**, including `desktop/wol_setup.py` and `desktop/wol_onboarding.py`. The one-time Wake-on-LAN onboarding state (`wol_onboarding.json`, any case or nesting) is private and rejected from payloads. The original multi-resolution `assets/droidbridge.ico` is hash-inventoried with the source, embedded via PyInstaller `--icon`, copied to runtime `assets/`, and supplied to Inno Setup through an absolute `/DIconFile` and `SetupIconFile`. The code includes the shared native UI theme `desktop/theme.py`, `desktop/update_protocol.py`, `desktop/update_manager.py` and `desktop/update_helper.py`. Update runtime state (`update_state.json`, any case or nesting) is private and rejected from payloads. Publishing private keys must never enter staged source or release exports; an embedded public verification key is expected and is not a secret. The launcher does not automatically start services. Setup creates no startup task, service, router forwarding or firewall rule. Runtime preferences, tokens and uploads remain outside the install tree under `%LOCALAPPDATA%/VzaimoPult`; uninstall deliberately preserves them.

## First-run Wake-on-LAN prerequisite

Before creating a new pair, Windows 1.0.7 requires one-time Wake-on-LAN setup embedded inside **«Подключение»** (Connection), not the regular Wake PC diagnostics section. Complete **«Проверить и завершить настройку»**, then explicitly choose **«Продолжить сопряжение»**. Completion requires a fresh check showing Magic Packet **enabled** on the same physical adapter, plus explicit manual BIOS/UEFI and local-network compatibility acknowledgements. Disabled, unsupported or unknown Windows capability cannot complete the step. Startup reads local completion only, with zero Windows probes; a fresh check runs only for explicit new pairing. Saved completion matching the same adapter with Magic Packet still enabled bypasses setup. A changed adapter or unconfirmed setting blocks new pairing until setup is completed again. This is not a reminder on every launch and must not disconnect an existing working pair. The check is not proof of successful waking; neither a completed step nor 100% can establish that. BIOS changes are manual, and Windows changes require confirmation and UAC approval. No automatic shutdown, BIOS entry or administrator action is part of installer startup.

## Build recipe

Use an isolated Python x64 environment with Tcl/Tk (tested host: Python 3.15). Dependencies are pinned in `requirements-build.txt`; this is a repeatable recipe, **not a bit-for-bit reproducible PE claim**. Python/wheel provenance, compiler versions, signing and timestamps also matter.

```powershell
python -m venv packaging/.venv-build
packaging/.venv-build/Scripts/python.exe -m pip install --only-binary=:all: -r packaging/requirements-build.txt
python -m unittest discover -s packaging -p "test*.py"
python packaging/acquire_inno.py
# Slim build: optional local media discovery remains available, no FFmpeg shipped.
packaging/.venv-build/Scripts/python.exe packaging/build_windows.py --output packaging/.build/slim-release-01 --iscc packaging/.build-tools/inno-7.1.1/ISCC.exe
# Bundled build: only after the complete media kit and final source receive root GO.
packaging/.venv-build/Scripts/python.exe packaging/build_windows.py --output packaging/.build/bundled-release-01 --media-root X:/reviewed-media-kit --iscc packaging/.build-tools/inno-7.1.1/ISCC.exe
python packaging/audit_artifact.py --output packaging/.build/bundled-release-01 --source .
```

Use a fresh output each time. Do not run the freezer while source or the media kit is still being edited. Do not install/uninstall on the owner's machine as a packaging smoke test. An existing installation's registration must not be overwritten by an allegedly isolated test. Root coordinates any real upgrade. Inno Setup 7.1.1 is SHA256-checked and unpacked without global installation; its compiler license must be reviewed for commercial use. The compiler/toolchains are not shipped.

The default slim setup omits FFmpeg/ffplay and never downloads media programs automatically. The optional bundled setup takes a **reviewed complete source-built kit**, not a folder of opaque third-party executables. The old hardcoded Gyan/local-only branch is removed. Packaging does not execute a kit's binaries during validation; a separate functional review must prove their behavior and provenance.

## Frozen media kit contract: schema 1

The producer supplies exactly these top-level fields in UTF-8 `media-manifest.json`:

```json
{
  "schema_version": 1,
  "runtime_sha256": {
    "bin/ffmpeg.exe": "<64 lowercase hexadecimal characters>",
    "bin/ffplay.exe": "<64 lowercase hexadecimal characters>",
    "bin/avcodec-62.dll": "<64 lowercase hexadecimal characters>"
  },
  "source_sha256": {
    "sources/ffmpeg-9.0.2.tar.xz": "<sha256>",
    "sources/build-media.sh": "<sha256>"
  },
  "license_sha256": {
    "licenses/FFmpeg-LGPL.txt": "<sha256>"
  },
  "components": [{
    "name": "FFmpeg",
    "version": "9.0.2",
    "license": "LGPL-2.1-or-later",
    "source_url": "https://ffmpeg.org/releases/ffmpeg-9.0.2.tar.xz",
    "source_paths": ["sources/ffmpeg-9.0.2.tar.xz"],
    "license_paths": ["licenses/FFmpeg-LGPL.txt"]
  }]
}
```

The example illustrates structure, not valid hashes or a complete runtime/dependency list. Every distributed FFmpeg dependency needs its own component entry with exact version/license, upstream HTTPS source URL, nonempty archive reference(s) and included license reference(s). Include official source archives, modifications if any, and sufficient source-build recipes. The current producer targets minimal LGPL FFmpeg with SDL2 and nv-codec-headers; MinGW runtime notices and applicable GCC exception must also be included as appropriate. Review complete dependency/source/license coverage independently; self-declared metadata alone cannot establish it.

`runtime_sha256`, `source_sha256`, and `license_sha256` are the **entire kit allowlist**, plus only `media-manifest.json` itself. All maps are nonempty. Runtime entries are direct `bin/*.exe` or `bin/*.dll`; both exact names `bin/ffmpeg.exe` and `bin/ffplay.exe` are mandatory. Sources require at least one `.tar.xz`, `.tar.gz`, `.tar.bz2`, `.tar.zst`, `.tgz` or `.zip` archive and a `.sh`, `.py`, `.ps1`, `.md` or `.txt` recipe. Each component references at least one source archive. Paths are portable, relative, forward-slash paths in their designated subtree. No traversal, backslashes, drive/ADS syntax, Windows reserved names, case-insensitive collisions, trailing-dot/space aliases, symlinks, junctions/reparse points, devices, unlisted files or unused directories are allowed. Every listed file must be regular and match SHA256. PE files outside runtime are rejected. Unknown schema fields, duplicate JSON keys, nonfree metadata and enabled nonfree configuration in text recipes are rejected.

Validation happens **before source staging/freezing**. The kit is validated again while copying and after staging. The entire kit ships under `payload/media/`: `bin/ffmpeg.exe` becomes `media/ffmpeg.exe`, every DLL is beside it, while `sources/`, `licenses/`, and `media-manifest.json` remain nested/preserved. The existing resolver can find the executables without PATH changes. Inno Setup's recursive payload rule includes all archives, recipes and licenses, not just executables. Hashes and complete component metadata are also captured as `media_bundle` in the build manifest. Do not modify the kit after verification.

## Integrity is not release permission

Builds always start with `public_release_ready: false`. The build manifest records source/payload SHA256, Python/dependency versions, frozen self-test, `contains_ffmpeg`, and media proof. `audit_artifact.py --output ... --source ...` checks source equality, payload and installer integrity, known runtime-secret exclusions, and the **full staged media kit** whenever `contains_ffmpeg` is true, even when the release flag is already true. Missing source proof is an audit failure, not an integrity-only success. Declaring `contains_ffmpeg: false` cannot hide an existing media directory or FFmpeg executable.

`integrity_ok: true` and `media_source_verified: true` mean the declared included files match, **not legal approval or runtime correctness**. `publish_allowed` also requires root's explicit `public_release_ready: true`. Root must first review provenance/source completeness/license obligations, actual media functionality, source privacy, frozen runtime self-test, real pairing, and installer/upgrade behavior. No publication or owner installation is performed by these scripts automatically. Code signing/SmartScreen trust is not supplied.

The frozen `--self-test OUTPUT_JSON` checks Python/TLS/Pillow and imports production components without calling their main functions, binding sockets or touching real runtime data. It is not a real phone integration or installation test. A payload-isolated smoke test must not claim isolated installer/uninstaller validation when existing owner registration prevents it.

Application sources are positive-allowlisted, not recursively copied. Tokens, custom apps/settings, logs, PIDs, keystores and private diagnostics do not enter staging. Do not export `.build`, `.build-tools`, `.venv-build`, build logs (host paths), or caches as project source. A frozen executable does not acquire later source changes: rebuild only from the final integrated source after root GO.
