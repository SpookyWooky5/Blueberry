#!/bin/bash
# ############################################################################ #
#                              MAINTENANCE HISTORY                             #
# ############################################################################ #
# DATE         Description
# ------------ -----------------------------------------------------------------
# 19-MAY-2025  Initial Draft
# 26-FEB-2026  v2 Changes
# ============================================================================ #

export USER="mainberry"
export DEV="/home/mainberry/Blueberry"
export PYTHONPATH="$DEV:$PYTHONPATH"
export LOG_DIR="/home/mainberry/Logs"
export BCFG="$DEV/Configs"
export PROMPTS_DIR="$DEV/prompts"
export VAULT_DIR="/home/mainberry/Vault"
VENV_PATH="$DEV/.venv"
LOG_FILE="$LOG_DIR/cron.log"
BASH_ALIASES="$HOME/.bash_aliases"

# Ensure we are using bash
[ -n "$BASH_VERSION" ] || exec /bin/bash "$0" "$@"

# Load aliases and env variables
if [ -f "$BASH_ALIASES" ]; then
  source "$BASH_ALIASES"
fi

# Activate virtual environment
source "$VENV_PATH/bin/activate"

# Load bash aliases (contains custom exports)
# . /home/mainberry/.bash_aliases

# ---[ Logging ]---
{
  echo -e "\n--- $(date '+%Y-%m-%d %H:%M:%S') ---"
  echo "Running: python $*"
  python "$@"
} >> "$LOG_FILE" 2>&1
