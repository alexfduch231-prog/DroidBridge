# Windows packaging implementation plan

Goal: per-user VzaimoPult setup, frozen Python runtime, explicit consent launcher; no personal files.
Architecture: one PyInstaller onedir executable dispatches server/viewer through adapters, with immutable allowlisted modules and writable LOCALAPPDATA/VzaimoPult. Inno Setup produces a per-user installer without services, autostart or firewall changes. Parent owns pairing and production modules.
Alternatives: onefile repeatedly extracts and complicates media licensing; MSIX requires identity/signing; onedir + Inno chosen for transparent files and ordinary uninstall.

Constraints: modify packaging/ and desktop/ only; no production server/viewer starts; no global installs; no token/apps/log/pid/keystore copies. Binary reproducibility is not guaranteed (PE timestamps/signing/toolchain); versions and file hashes recorded.

1. Write allowlist/symlink/secret exclusion and launcher validation tests; run red.
2. Implement isolated source staging and hash inventory; run green.
3. Implement desktop command validation and adapter paths; GUI offers explicit server start/stop and phone-IP viewer launch. Pairing integration stays parent-owned.
4. Pin build dependency versions in isolated venv; freeze explicit modules; collect upstream Python/Pillow licenses; execute self-test only (no network or runtime data).
5. Import separately licensed FFmpeg only with complete version/license/source metadata; never silently download 436 MiB local full-build binaries.
6. Acquire official Inno compiler into build-tools without global installation, compile per-user installer, verify setup hash and frozen diagnostic.

Review focus: symlink escapes, unexpected source files, missing runtime prerequisites, port collisions, stale child processes. Unit tests cover first three; server startup is not integration-tested because production processes must remain untouched. Parent reviews final integrated sources before rebuild/release.
