#!/bin/sh
set -eu
# Atualiza a cópia incluída na imagem sem atrasar o arranque do serviço.
printf '%s\n' 'DatabaseDirectory /var/lib/clamav' 'DatabaseMirror database.clamav.net' 'Checks 4' > /tmp/rovuma-freshclam.conf
clamscan --no-summary /etc/debian_version
python -m ops.verify_processor
freshclam --config-file=/tmp/rovuma-freshclam.conf --daemon --foreground >/dev/null 2>&1 &
exec python -m documents.remote_processor
