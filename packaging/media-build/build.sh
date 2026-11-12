#!/bin/sh
set -eu
# Run with w64devkit 2.11.0 sh, not MSYS bash. ROOT may be overridden.
ROOT=${ROOT:-$(cd "$(dirname "$0")/.." && pwd)}
TOOLS="$ROOT/.build-tools/media/w64devkit"
WORK="$ROOT/.build/media-minimal-01"
export PATH="$TOOLS/bin;$PATH"
PREFIX="$WORK/prefix"
SDL="$WORK/SDL2-2.32.10/x86_64-w64-mingw32"
mkdir -p "$PREFIX" "$WORK/build-ffmpeg"
cd "$WORK/nv-codec-headers-13.0.19.0"
make PREFIX="$PREFIX" install
# Override original development .pc absolute cross-build prefix without touching headers/libraries.
mkdir -p "$PREFIX/lib/pkgconfig"
# w64devkit u-config relocates pc prefix to its containing install tree.
cp -R "$SDL/include/SDL2" "$PREFIX/include/"
cp "$SDL/lib/libSDL2.dll.a" "$SDL/lib/libSDL2main.a" "$PREFIX/lib/"
printf 'prefix=%s\nexec_prefix=${prefix}\nlibdir=${prefix}/lib\nincludedir=${prefix}/include\n\nName: sdl2\nDescription: SDL2\nVersion: 2.32.10\nLibs: -L${libdir} -lmingw32 -lSDL2main -lSDL2 -mwindows\nCflags: -I${includedir}/SDL2 -Dmain=SDL_main\n' "$SDL" > "$PREFIX/lib/pkgconfig/sdl2.pc"
export PKG_CONFIG_PATH="$PREFIX/lib/pkgconfig"
cd "$WORK/build-ffmpeg"
sh ../ffmpeg-9.0.2/configure --prefix=../prefix --target-os=mingw32 --arch=x86_64 --cc=gcc --cxx=g++ --enable-shared --disable-static --disable-autodetect --disable-gpl --disable-nonfree --disable-version3 --disable-doc --disable-debug --disable-x86asm --disable-ffprobe --disable-everything --enable-ffmpeg --enable-ffplay --enable-sdl2 --enable-ffnvcodec --enable-nvenc --enable-d3d11va --enable-w32threads --disable-pthreads --disable-vulkan --enable-decoder=h264,aac,pcm_s16le,rawvideo,wrapped_avframe --enable-encoder=h264_nvenc,aac,pcm_s16le,rawvideo,wrapped_avframe --enable-parser=h264,aac --enable-demuxer=h264,aac,pcm_s16le,rawvideo,wav,mov --enable-muxer=h264,adts,pcm_s16le,rawvideo,null,wav --enable-protocol=file,pipe,tcp,http,udp --enable-indev=lavfi --enable-filter=ddagrab,hwdownload,format,scale,aresample,aformat,anull,null,color,testsrc2,sine --enable-bsf=h264_metadata,h264_mp4toannexb,aac_adtstoasc --extra-cflags='-ffile-prefix-map=../ffmpeg-9.0.2=ffmpeg-9.0.2 -fdebug-prefix-map=../ffmpeg-9.0.2=ffmpeg-9.0.2' --extra-ldflags=-static-libgcc > "$WORK/configure.log" 2>&1
make -j8 > "$WORK/make.log" 2>&1
make install > "$WORK/install.log" 2>&1
mkdir -p "$WORK/media-kit/bin"
cp "$PREFIX/bin/"*.dll "$PREFIX/bin/ffmpeg.exe" "$PREFIX/bin/ffplay.exe" "$WORK/media-kit/bin/"
cp "$SDL/bin/SDL2.dll" "$WORK/media-kit/bin/"
"$WORK/media-kit/bin/ffmpeg.exe" -version > "$WORK/version.txt" 2>&1
"$WORK/media-kit/bin/ffplay.exe" -version >> "$WORK/version.txt" 2>&1
