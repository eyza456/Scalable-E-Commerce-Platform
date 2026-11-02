#!/usr/bin/env bash
set -euo pipefail
backup="${1:?Uso: $0 directorio-backup}"
[[ -f "$backup/SHA256SUMS" ]] || { echo "Falta SHA256SUMS" >&2; exit 1; }
(cd "$backup" && sha256sum -c SHA256SUMS)
echo "Backup integro: $backup"
