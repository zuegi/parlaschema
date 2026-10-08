#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
env_file="$HOME/.config/parlaschema/apertus.env"

if [ ! -f "$env_file" ] || [ ! -r "$env_file" ]; then
    printf '%s\n' "Missing or unreadable config file: $env_file" >&2
    exit 1
fi

unset LLM_NAME LLM_BASE_URL LLM_API_KEY
. "$env_file"

if [ -z "${LLM_NAME:-}" ]; then
    printf '%s\n' 'Missing or empty LLM_NAME in apertus.env' >&2
    exit 1
fi
if [ -z "${LLM_BASE_URL:-}" ]; then
    printf '%s\n' 'Missing or empty LLM_BASE_URL in apertus.env' >&2
    exit 1
fi
if [ -z "${LLM_API_KEY:-}" ]; then
    printf '%s\n' 'Missing or empty LLM_API_KEY in apertus.env' >&2
    exit 1
fi

export LLM_NAME LLM_BASE_URL LLM_API_KEY
cd "$script_dir/.."
exec uv run --frozen openparl-extractor check-config
