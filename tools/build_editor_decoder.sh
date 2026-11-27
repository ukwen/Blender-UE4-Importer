#!/usr/bin/env bash
# Build locally from separately obtained pinned sources (see development docs).
set -euo pipefail
if [ "$#" != 3 ]; then echo "usage: $0 PYOOZ_DIR BLAKE3_C_DIR OUTPUT_EXECUTABLE" >&2; exit 2; fi
here=$(cd "$(dirname "$0")" && pwd)
ooz=$(realpath "$1"); b3=$(realpath "$2"); output=$(realpath -m "$3")
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
for name in blake3 blake3_dispatch blake3_portable; do
  cc -O2 -DBLAKE3_NO_SSE2 -DBLAKE3_NO_SSE41 -DBLAKE3_NO_AVX2 -DBLAKE3_NO_AVX512 -DBLAKE3_USE_NEON=0 -I"$b3" -c "$b3/$name.c" -o "$tmp/$name.o"
done
g++ -O2 -msse4.1 -I"$ooz" -I"$b3" "$here/editor_payload_decoder.cpp" "$ooz/kraken.cpp" "$ooz/bitknit.cpp" "$ooz/lzna.cpp" "$tmp"/*.o -o "$output"
