#!/bin/sh
# Neon Minutes for Linux x86_64: self-extracting installer.
#   sh NeonMinutes-<version>-linux-x86_64.run            wizard (or terminal without a desktop)
#   sh NeonMinutes-<version>-linux-x86_64.run --help     options
# Unpacks the bundled Python and the program in a temporary folder and runs the installer,
# which puts everything in the user's home (no root needed).
set -e
if [ "$(uname -s)" != "Linux" ] || [ "$(uname -m)" != "x86_64" ]; then
    echo "Neon Minutes: questo installer è per Linux x86_64 (questo sistema è $(uname -s) $(uname -m))." >&2
    exit 1
fi
TMP=$(mktemp -d "${TMPDIR:-/tmp}/neon-minutes.XXXXXX")
trap 'rm -rf "$TMP"' EXIT INT TERM
echo "Neon Minutes: estrazione dell'installer..."
LINE=$(awk '/^__NEON_MINUTES_PAYLOAD__$/ { print NR + 1; exit 0 }' "$0")
tail -n +"$LINE" "$0" | tar -xz -C "$TMP"
"$TMP/payload/runtime/bin/python3" -s -E "$TMP/payload/installer/linux_setup.py" --payload "$TMP/payload" "$@"
exit $?
__NEON_MINUTES_PAYLOAD__
