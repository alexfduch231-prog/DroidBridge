# Minimal Windows media build spike

Scope: media-build, .build-tools/media and .build/media-minimal-01 only. Do not install, publish, modify listener or owner configuration.

1. Pin official FFmpeg 9.0.2 source, SDL 2.32.10 MinGW development binaries and exact source, nv-codec-headers 13.0.19.0, w64devkit 2.11.0. Verify known upstream hashes and record all computed hashes.
2. Build shared LGPL FFmpeg with external autodetection disabled; explicitly SDL2, ffnvcodec/NVENC and D3D11VA. Limit codecs/formats/filters to current stream and pipe playback plus simple test generators. No GPL/nonfree/external codec libraries. Disable external x86 assembly for this spike (no NASM dependency).
3. Preserve original source archives, configure recipe and logs; inspect PE imports, versions and capabilities; smoke-test synthetic encode/decode and ffplay headless audio. Do not imply desktop/GPU testing from capability listing.
4. Supply runtime/source bundle plus exact manifest to lead for independent integration/review.

Ruling: use nv-codec-headers 13.0.19.0 rather than latest 13.1.15.0: latest requires driver >=610; 13.0 requires >=570. Record runtime driver restriction and prefer oldest FFmpeg-supported header version if configure permits.
Ruling: use shared FFmpeg and official SDL2 DLL; owner application invokes executables, not libraries. Keep all runtime licensing/source notices and replaceability.

Research evidence: BtbN download cache is 2,243,239,670 bytes with a 2026-11-25 expiry, not complete demonstrated Cargo closure; MSYS2 entails large DLL/source closure. Self-build gives controlled dependencies. No build success claimed yet.
