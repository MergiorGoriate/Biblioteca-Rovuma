#!/usr/bin/env bash
# Executar na raiz, com o repositório externo Restic configurado no ambiente.
set -euo pipefail
: "${RESTIC_REPOSITORY:?Defina o destino externo}"
: "${RESTIC_PASSWORD_FILE:?Defina a localização da senha Restic}"
case "$RESTIC_REPOSITORY" in
    /*|./*|../*|local:*) echo "Seleccione um destino de cópia externo." >&2; exit 1 ;;
esac
umask 077
backup=$(mktemp -d)
stopped=0
finish() {
    result=$?
    trap - EXIT
    if [ "$stopped" = 1 ]; then docker compose start web dispatcher || result=1; fi
    rm -rf "$backup"
    if [ "$result" = 0 ]; then
        printf '%s Cópia concluída\n' "$(date -u +%FT%TZ)"
    else
        printf '%s Falha na cópia\n' "$(date -u +%FT%TZ)" >&2
        if [ -n "${BACKUP_ALERT_COMMAND:-}" ]; then "$BACKUP_ALERT_COMMAND" || true; fi
    fi
    exit "$result"
}
trap finish EXIT
trap 'exit 1' INT TERM
mkdir "$backup/private"
stopped=1
docker compose stop web dispatcher
docker compose exec -T db sh -ec 'pg_dump -Fc -U "$ROVUMA_DB_USER" "$POSTGRES_DB"' > "$backup/rovuma.dump"
docker compose run --rm --no-deps -T web tar -C /data/private --exclude=./incoming -cf - . | tar -C "$backup/private" -xf -
docker compose start web dispatcher
stopped=0
(cd "$backup" && restic backup --tag biblioteca-rovuma rovuma.dump private)
restic forget --tag biblioteca-rovuma --group-by host,tags --keep-daily "${KEEP_DAILY:-14}" \
    --keep-weekly "${KEEP_WEEKLY:-8}" --keep-monthly "${KEEP_MONTHLY:-12}" --prune
