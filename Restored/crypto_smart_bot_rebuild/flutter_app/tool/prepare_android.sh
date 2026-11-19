#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v flutter >/dev/null 2>&1; then
  echo "ERROR: Flutter SDK is not installed or not on PATH." >&2
  exit 127
fi

flutter create --platforms=android --org com.cryptosmartbot --project-name crypto_smart_bot .

MANIFEST="android/app/src/main/AndroidManifest.xml"
if [[ ! -f "$MANIFEST" ]]; then
  echo "ERROR: Flutter did not generate $MANIFEST" >&2
  exit 2
fi

python3 - "$MANIFEST" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
s = p.read_text()
permission = '    <uses-permission android:name="android.permission.INTERNET" />'
if 'android.permission.INTERNET' not in s:
    s = s.replace('<manifest ', '<manifest ', 1)
    marker = '<application'
    if marker not in s:
        raise SystemExit('Could not find application tag in Android manifest')
    s = s.replace(marker, permission + '\n    ' + marker, 1)
if 'android:usesCleartextTraffic=' not in s:
    s = s.replace('<application', '<application android:usesCleartextTraffic="true"', 1)
p.write_text(s)
PY

echo "Android project prepared. Local HTTP is enabled for development LAN use only."
echo "For public deployment, use HTTPS and disable cleartext traffic."
