#!/bin/sh
# Sign the Peaks macOS app bundle on a protected release runner.
set -eu

target=${1:?a signing target is required}
identity=${PEAKS_MACOS_SIGN_IDENTITY:-}
if [ -z "$identity" ]; then
  echo "PEAKS_MACOS_SIGN_IDENTITY is required for a release signature" >&2
  exit 1
fi
if [ ! -e "$target" ]; then
  echo "signing target does not exist: $target" >&2
  exit 1
fi

# Sign nested code before the app bundle. The explicit pass avoids relying on
# --deep to discover every native helper in a PyInstaller bundle.
if [ -d "$target" ]; then
  find "$target" -type f \( -name '*.dylib' -o -name '*.so' -o -name '*.framework' \) -print0 |
    while IFS= read -r -d '' file; do
      codesign --force --options runtime --timestamp --sign "$identity" "$file"
    done
  codesign --force --deep --options runtime --timestamp --sign "$identity" "$target"
else
  codesign --force --options runtime --timestamp --sign "$identity" "$target"
fi
codesign --verify --deep --strict --verbose=2 "$target"
