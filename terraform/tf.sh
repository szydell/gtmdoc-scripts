#!/usr/bin/env bash
# tf.sh — wrapper terraform z profilem AWS mumps-terraform
# Użycie:
#   ./tf.sh plan
#   ./tf.sh apply
#   ./tf.sh destroy
#   ./tf.sh output route53_nameservers
#   ./tf.sh <dowolna komenda terraform>

set -euo pipefail

PROFILE="${AWS_PROFILE:-mumps-terraform}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

cd "$SCRIPT_DIR"

export AWS_PROFILE="$PROFILE"
echo "→ AWS_PROFILE=$AWS_PROFILE"

exec terraform "$@"
