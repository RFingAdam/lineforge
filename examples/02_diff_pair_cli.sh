#!/usr/bin/env bash
# Phase 1 example — CLI usage.
#
# Calculate Z0 / Zdiff for a few common stackups via the atlc3 CLI.
#
# Run from the repo root after `pip install -e .`:
#   bash examples/02_diff_pair_cli.sh

set -euo pipefail

echo "=== 50Ω microstrip on 4 mil FR4 ==="
atlc3 solve --type microstrip --W 6mil --H 4mil --T 1.4mil --er 4.4

echo
echo "=== 100Ω diff pair on 4 mil FR4 ==="
atlc3 solve \
    --type edge_coupled_diff_microstrip \
    --W 4mil --S 6mil --H 4mil --T 1.4mil --er 4.4

echo
echo "=== 50Ω stripline on 14 mil FR4 cavity ==="
atlc3 solve --type stripline_symmetric --W 5mil --T 1.4mil --B 14mil --er 4.4

echo
echo "=== CPWG 50Ω target ==="
atlc3 solve --type cpwg --W 5mil --S 8mil --H 4mil --T 1.4mil --er 4.4

echo
echo "=== JSON output for piping to jq, csv tools, etc. ==="
atlc3 solve --type microstrip --W 6mil --H 4mil --T 1.4mil --er 4.4 \
    --frequency 1GHz --output json
