# Minimal media kit acceptance

- Inputs: FFmpeg 9.0.2, SDL2 2.32.10 complete source and exact MinGW development archive, nv-codec-headers 13.0.19.0; all pinned SHA-256 in fetch.sh.
- Build-only toolchain: official w64devkit 2.11.0 x64, GCC 16.2.0. Toolchain source URL preserved in generated BUILD.md. Toolchain executable is not redistributed in the application payload.
- FFmpeg: shared, no GPL/nonfree/version3, no external autodetection; no libx264. Software H.264 decode and NVIDIA hardware H.264 encode are intentionally different capabilities.
- SDL2 DLL dynamic; SDL2main static startup shim from matching upstream development archive, with complete matching SDL source and zlib notice.
- Compiler runtime: MinGW notice, GPLv3 text and GCC runtime exception retained; standard Windows DLLs are operating-system prerequisites and are not copied.
- Build recipe/source archives/notices must remain alongside distributed binaries. Replaceable shared libraries must not be prevented by EULA or integrity enforcement outside a controlled updater flow; integration/legal review is separate.
- Runtime gate: capability listings, synthetic NVENC H.264 encode, native H.264 decode, ffplay playback, AAC/PCM generation and playback. This does not prove phone playback, desktop capture, or performance on arbitrary GPUs.
- No desktop capture performed by automatic verification. NVIDIA >=570 and compatible GPU are external prerequisites.
- PE gate: every import is either provided in kit or explicit Windows system DLL; scan UTF-8 and UTF-16 strings for private build paths.
- Manifest: strict schema_version=1, runtime_sha256/source_sha256/license_sha256 and components; every allowed file hashed. No logs or synthetic test media in kit.
- This is a technical provenance checklist, not legal advice or patent clearance.
