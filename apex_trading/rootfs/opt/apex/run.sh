#!/usr/bin/with-contenv bashio
# ==============================================================================
# APEX Trading AI — Add-on Run Script
# This is the direct container entrypoint. No s6-overlay needed.
# The HA Supervisor calls this script as PID 1 via /usr/bin/with-contenv.
# ==============================================================================
set -e

bashio::log.info "╔══════════════════════════════════╗"
bashio::log.info "║   APEX Trading AI  v1.0.0        ║"
bashio::log.info "╚══════════════════════════════════╝"

# ── Data directory ────────────────────────────────────────────
DATA_DIR="/data/apex"
bashio::log.info "Initialising data directory: ${DATA_DIR}"
mkdir -p "${DATA_DIR}"

for f in trades.json optlog.json analyses.json; do
    [ -f "${DATA_DIR}/${f}" ] || echo "[]" > "${DATA_DIR}/${f}"
done
[ -f "${DATA_DIR}/state.json" ] || echo "{}" > "${DATA_DIR}/state.json"

# ── Read configuration from HA options ───────────────────────
bashio::log.info "Loading configuration..."

export ANTHROPIC_API_KEY="$(bashio::config 'anthropic_api_key')"
export MARKET_DATA_SOURCE="$(bashio::config 'market_data_source')"
export MARKET_DATA_KEY="$(bashio::config 'market_data_key')"
export TRADING_MODE="$(bashio::config 'trading_mode')"
export RISK_LEVEL="$(bashio::config 'risk_level')"
export TAX_BRACKET="$(bashio::config 'tax_bracket')"
export STOP_LOSS_PCT="$(bashio::config 'stop_loss_pct')"
export TAKE_PROFIT_PCT="$(bashio::config 'take_profit_pct')"
export MAX_POSITION_PCT="$(bashio::config 'max_position_pct')"
export DAILY_LOSS_LIMIT="$(bashio::config 'daily_loss_limit')"
export AUTO_ANALYSIS_INTERVAL="$(bashio::config 'auto_analysis_interval')"
export BROKER_PLATFORM="$(bashio::config 'broker_platform')"
export BROKER_API_URL="$(bashio::config 'broker_api_url')"
export BROKER_API_KEY="$(bashio::config 'broker_api_key')"
export BROKER_API_SECRET="$(bashio::config 'broker_api_secret')"
export LOG_LEVEL="$(bashio::config 'log_level')"
export DATA_DIR="${DATA_DIR}"
export PORT=7123

bashio::log.info "Trading mode : ${TRADING_MODE}"
bashio::log.info "Market data  : ${MARKET_DATA_SOURCE}"
bashio::log.info "Port         : ${PORT}"
bashio::log.info "Data dir     : ${DATA_DIR}"

# ── Launch the Python server ──────────────────────────────────
bashio::log.info "Starting APEX server..."
exec python3 /opt/apex/server.py
