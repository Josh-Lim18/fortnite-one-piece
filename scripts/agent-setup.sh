#!/bin/sh
# Run it once, first: the reset discards anything already on this branch.
set -eu
base="${1:?usage: scripts/agent-setup.sh <base-ref>, e.g. main}"
git reset -q --hard "$base"
git config user.name "Owen Yan"
git config user.email "100368790+owenbonc@users.noreply.github.com"
