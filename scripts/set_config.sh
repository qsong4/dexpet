#!/usr/bin/env bash
# Configure LLM via HTTP. Usage:
#   ./scripts/set_config.sh sk-xxx
#   ./scripts/set_config.sh sk-xxx https://api.deepseek.com deepseek-chat deepseek
#   ./scripts/set_config.sh sk-xxx https://api.openai.com/v1 gpt-4o-mini custom
set -euo pipefail
API_KEY="${1:?api_key required}"
BASE_URL="${2:-https://api.deepseek.com}"
MODEL="${3:-deepseek-chat}"
PRESET="${4:-deepseek}"
PORT="${DEXPET_PORT:-8765}"
curl -sS -X PUT "http://127.0.0.1:${PORT}/config" \
  -H 'Content-Type: application/json' \
  -d "{\"provider_preset\":\"${PRESET}\",\"base_url\":\"${BASE_URL}\",\"model\":\"${MODEL}\",\"api_key\":\"${API_KEY}\"}"
echo
