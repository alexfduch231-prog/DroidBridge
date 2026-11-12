#!/bin/bash
set -euo pipefail
ROOT=${ROOT:-$(cd "$(dirname "$0")/.." && pwd)}
DL="$ROOT/.build-tools/media/downloads"
mkdir -p "$DL" "$ROOT/.build/media-minimal-01"
fetch() {
  local name="$1" url="$2" expected="$3"
  if [[ ! -f "$DL/$name" ]]; then curl --ssl-revoke-best-effort -fL --retry 2 "$url" -o "$DL/$name.part"; mv "$DL/$name.part" "$DL/$name"; fi
  local actual; actual=$(sha256sum "$DL/$name"); echo "$actual"
  if [[ "$expected" != unknown ]]; then [[ "${actual%% *}" == "$expected" ]] || exit 11; fi
}
fetch ffmpeg-9.0.2.tar.xz https://ffmpeg.org/releases/ffmpeg-9.0.2.tar.xz 8c3850283eb25fa026482078a04051e0be17347b09ef81a0849bec15a96e002e
fetch SDL2-devel-2.32.10-mingw.tar.gz https://github.com/libsdl-org/SDL/releases/download/release-2.32.10/SDL2-devel-2.32.10-mingw.tar.gz 83a5d74012311edc3c0d40ea6faecbe57ad692aa033fa5dc273cc937e3938ff2
fetch SDL2-2.32.10.tar.gz https://github.com/libsdl-org/SDL/releases/download/release-2.32.10/SDL2-2.32.10.tar.gz 5f5993c530f084535c65a6879e9b26ad441169b3e25d789d83287040a9ca5165
fetch nv-codec-headers-13.0.19.0.tar.gz https://github.com/FFmpeg/nv-codec-headers/releases/download/n13.0.19.0/nv-codec-headers-13.0.19.0.tar.gz 13da39edb3a40ed9713ae390ca89faa2f1202c9dda869ef306a8d4383e242bee
fetch w64devkit-x64-2.11.0.7z.exe https://github.com/skeeto/w64devkit/releases/download/v2.11.0/w64devkit-x64-2.11.0.7z.exe 54c2bb9962e8a30c8270e34c5efc3d5fee579f53087fa7d435b95fbba2af7b2b
cd "$ROOT/.build/media-minimal-01"
tar xf "$DL/ffmpeg-9.0.2.tar.xz"
tar xf "$DL/SDL2-devel-2.32.10-mingw.tar.gz"
tar xf "$DL/nv-codec-headers-13.0.19.0.tar.gz"
cd "$ROOT/.build-tools/media"
"$DL/w64devkit-x64-2.11.0.7z.exe" -y -o. > extract.log
