#!/usr/bin/with-contenv bashio

export ADMIN_USER="$(bashio::config 'admin_user')"
export ADMIN_PASSWORD="$(bashio::config 'admin_password')"
export EXTERNAL_URL="$(bashio::config 'external_url')"
export API_TOKEN="$(bashio::config 'api_token')"
export MAX_UPLOAD_MB="$(bashio::config 'max_upload_mb')"
export ALLOW_REGISTRATION="$(bashio::config 'allow_registration')"
export SPRACHE="$(bashio::config 'sprache')"
export RETENTION_DAYS="$(bashio::config 'retention_days')"
export STUN_SERVER="$(bashio::config 'stun_server')"
export TURN_SERVER="$(bashio::config 'turn_server')"
export TURN_USERNAME="$(bashio::config 'turn_username')"
export TURN_PASSWORD="$(bashio::config 'turn_password')"
export LOG_LEVEL="$(bashio::config 'log_level')"

mkdir -p /data/uploads

bashio::log.info "Chat Server startet auf Port 8099"
exec python3 /opt/chat/server.py
