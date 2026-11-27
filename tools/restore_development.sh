#!/usr/bin/env bash
# Linux x86-64 recovery from verified Library originals. Fresh directory only.
set -euo pipefail
if [ "$#" != 2 ]; then echo 'Usage: restore_development.sh ASSET_DIRECTORY NEW_WORK_DIRECTORY' >&2; exit 2; fi
assets=$(realpath "$1"); work=$(realpath -m "$2"); here=$(cd "$(dirname "$0")/.." && pwd)
if [ -e "$work" ]; then echo 'Refusing to overwrite existing workspace' >&2; exit 2; fi
(cd "$assets"; sha256sum --check "$here/docs/RECOVERY_ASSETS.sha256")
mkdir -p "$work/runtime" "$work/deps"
tar -xJf "$assets/blender-4.2.4-linux-x64.tar.xz" -C "$work/runtime"
unzip -q "$assets/ShooterSam-UE5.6-editor.zip" -d "$work/runtime"
unzip -q "$assets/pyooz-fde8c26-source.zip" -d "$work/deps"
unzip -q "$assets/blake3-282d066-source.zip" -d "$work/deps"
bash "$here/tools/build_editor_decoder.sh" "$work/deps/pyooz" "$work/deps/blake3/c" "$work/decoder"
blender="$work/runtime/blender-4.2.4-linux-x64/blender"
"$blender" --version | head -n 1
# Quote paths for bash, never source unknown downloaded scripts.
printf 'export UE56_EDITOR_PROJECT=%q\nexport UE_EDITOR_PAYLOAD_DECODER=%q\nexport BLENDER=%q\n' "$work/runtime/ShooterSam/ShooterSam.uproject" "$work/decoder" "$blender" > "$work/environment.sh"
source "$work/environment.sh"
(cd "$here"; python -m unittest discover -s tests -p 'test_*.py')
