#!/usr/bin/env bash
# tf.sh — wrapper terraform z profilem AWS mumps-terraform
#
# Użycie:
#   ./tf.sh plan
#   ./tf.sh apply
#   ./tf.sh destroy
#   ./tf.sh output route53_nameservers
#   ./tf.sh <dowolna komenda terraform>
#
# Pierwsze uruchomienie (przed delegacją domeny):
#   ./tf.sh bootstrap
#   → Tworzy tylko hosted zone Route 53, wypisuje NS do podania rejestratorowi
#   Po delegacji NS i propagacji DNS uruchom: ./tf.sh apply

set -euo pipefail

PROFILE="${AWS_PROFILE:-mumps-terraform}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

cd "$SCRIPT_DIR"

export AWS_PROFILE="$PROFILE"
echo "→ AWS_PROFILE=$AWS_PROFILE"

if [[ "${1:-}" == "bootstrap" ]]; then
    echo "→ Tryb bootstrap: tworzę tylko Route 53 hosted zone"
    echo "→ Po apply podaj NS rejestratorowi, poczekaj na propagację, potem: ./tf.sh apply"
    echo ""
    terraform apply -target=aws_route53_zone.site
    echo ""
    echo "=== Serwery NS do podania rejestratorowi ==="
    terraform output route53_nameservers
    exit 0
fi

exec terraform "$@"
