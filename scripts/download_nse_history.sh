#!/bin/zsh
set -euo pipefail

START="${1:-2006-01-01}"
END="${2:-$(date +%F)}"
ROOT="${3:-data/raw/nse/bhavcopy}"
PYTHON="${PYTHON:-python3}"
mkdir -p "$ROOT"

validate_archive() {
  "$PYTHON" scripts/validate_nse_archive.py "$1" >/dev/null 2>&1
}

current="$START"
while [[ "$current" < "$END" || "$current" == "$END" ]]; do
  weekday=$(date -j -f '%Y-%m-%d' "$current" '+%u')
  if [[ "$weekday" -le 5 ]]; then
    y=$(date -j -f '%Y-%m-%d' "$current" '+%Y')
    d=$(date -j -f '%Y-%m-%d' "$current" '+%d')
    m=$(date -j -f '%Y-%m-%d' "$current" '+%b' | tr '[:lower:]' '[:upper:]')
    target="$ROOT/${current}.zip"
    if [[ ! -s "$target" ]]; then
      part="${target}.part.$$"
      legacy="https://archives.nseindia.com/content/historical/EQUITIES/${y}/${m}/cm${d}${m}${y}bhav.csv.zip"
      ymd=$(date -j -f '%Y-%m-%d' "$current" '+%Y%m%d')
      udiff="https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_${ymd}_F_0000.csv.zip"
      if curl -fsSL -A 'Mozilla/5.0' -e 'https://www.nseindia.com/' "$legacy" -o "$part" && validate_archive "$part"; then
        mv "$part" "$target"
      elif curl -fsSL -A 'Mozilla/5.0' -e 'https://www.nseindia.com/' "$udiff" -o "$part" && validate_archive "$part"; then
        mv "$part" "$target"
      else
        rm -f "$part"
      fi
      if [[ -s "$target" ]] && validate_archive "$target"; then
        printf '%s downloaded\n' "$current"
      else
        printf '%s missing or invalid\n' "$current" >&2
      fi
    elif ! validate_archive "$target"; then
      printf '%s cached file is invalid; refusing overwrite\n' "$current" >&2
    fi
  fi
  current=$(date -j -v+1d -f '%Y-%m-%d' "$current" '+%Y-%m-%d')
done
