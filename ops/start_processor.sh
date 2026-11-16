#!/bin/sh
set -eu
clamscan --no-summary /etc/debian_version
python -m ops.verify_processor
freshclam --config-file=/etc/freshclam.processor.conf --daemon --foreground &
exec python -m documents.remote_processor
