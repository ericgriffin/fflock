#!/bin/sh
rm -rf ~/ffmpeg_build ~/bin/{ffmpeg,ffprobe,ffserver,lame,vsyasm,x264,yasm,ytasm}

cd ~/ffmpeg_sources/x264
make distclean
git pull
./configure --prefix="$HOME/ffmpeg_build" --bindir="$HOME/bin" --enable-static
make && make install

cd ~/ffmpeg_sources/fdk_aac
make distclean
git pull
./configure --prefix="$HOME/ffmpeg_build" --disable-shared
make && make install

cd ~/ffmpeg_sources/libvpx
make clean
git pull
./configure --prefix="$HOME/ffmpeg_build" --disable-examples
make && make install

cd ~/ffmpeg_sources/ffmpeg
make distclean
git pull
./configure --prefix="$HOME/ffmpeg_build" --extra-cflags="-I$HOME/ffmpeg_build/include" --extra-ldflags="-L$HOME/ffmpeg_build/lib" --bindir="$HOME/bin" --extra-libs="-ldl" --enable-gpl --enable-nonfree --enable-libfdk_aac --enable-libmp3lame --enable-libopus --enable-libvorbis --enable-libvpx --enable-libx264 --enable-libfreetype --enable-libspeex --enable-libtheora
make && make install

