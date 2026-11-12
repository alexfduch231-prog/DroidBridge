#!/bin/sh
set -eu
ROOT=$(cd "$(dirname "$0")/.." && pwd)
export PATH="$ROOT/.build-tools/media/w64devkit/bin;$PATH"
PREFIX="$ROOT/.build/media-minimal-01/prefix"
SDL="$ROOT/.build/media-minimal-01/SDL2-2.32.10/x86_64-w64-mingw32"
cp -R "$SDL/include/SDL2" "$PREFIX/include/"
cp "$SDL/lib/libSDL2.dll.a" "$SDL/lib/libSDL2main.a" "$PREFIX/lib/"
printf 'prefix=%s\nName: sdl2\nDescription: SDL2\nVersion: 2.32.10\nLibs: -L${prefix}/lib -lmingw32 -lSDL2main -lSDL2 -mwindows\nCflags: -I${prefix}/include/SDL2 -Dmain=SDL_main\n' "$PREFIX" > "$PREFIX/lib/pkgconfig/sdl2.pc"
export PKG_CONFIG_PATH="$PREFIX/lib/pkgconfig"
pkg-config --cflags --libs sdl2
printf '#include <SDL_events.h>\nint main(int argc,char **argv){ SDL_Event e; return SDL_PollEvent(&e); }\n' > "$ROOT/.build/media-minimal-01/probe-sdl.c"
gcc $(pkg-config --cflags sdl2) "$ROOT/.build/media-minimal-01/probe-sdl.c" $(pkg-config --libs sdl2) -o "$ROOT/.build/media-minimal-01/probe-sdl.exe"
