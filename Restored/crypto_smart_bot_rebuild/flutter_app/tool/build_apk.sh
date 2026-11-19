#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
API_URL="${1:-${BOT_API_URL:-http://10.0.2.2:8000}}"
if [[ "$API_URL" != http://* && "$API_URL" != https://* ]]; then
  echo "BOT_API_URL must begin with http:// or https://" >&2
  exit 2
fi
if ! command -v flutter >/dev/null 2>&1; then
  echo "ERROR: Flutter SDK is required." >&2
  exit 127
fi
./tool/prepare_android.sh
flutter pub get
flutter build apk --release --dart-define="BOT_API_URL=$API_URL"
echo "APK: $ROOT/build/app/outputs/flutter-apk/app-release.apk"
