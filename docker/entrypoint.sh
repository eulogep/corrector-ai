#!/bin/sh
set -eu

# Le volume est créé par Docker avec des droits root sur certains hôtes.
# Ajuster uniquement les dossiers applicatifs nécessaires, puis abandonner root.
mkdir -p /data/uploads /data/reports /data/model-cache
chown -R corrector:corrector /data

exec setpriv --reuid=corrector --regid=corrector --init-groups "$@"
