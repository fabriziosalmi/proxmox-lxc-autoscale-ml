#!/bin/bash
#
# LXC AutoScale ML installer.

set -euo pipefail

# Log file
LOGFILE="lxc_autoscale_ml_installer.log"

# Define text styles and emojis
# Guarded: under `set -euo pipefail`, an unset or dumb TERM made tput fail and
# aborted the whole script at line 11 -- which is exactly the documented
# `curl | bash` case from cron or Ansible.
if [[ -t 1 ]] && command -v tput >/dev/null 2>&1 && tput setaf 1 >/dev/null 2>&1; then
    BOLD=$(tput bold); RESET=$(tput sgr0)
    GREEN=$(tput setaf 2); RED=$(tput setaf 1)
    YELLOW=$(tput setaf 3); BLUE=$(tput setaf 4)
else
    BOLD=""; RESET=""; GREEN=""; RED=""; YELLOW=""; BLUE=""
fi
CHECKMARK="\xE2\x9C\x85"
CROSSMARK="\xE2\x9D\x8C"
WARNING="\xE2\x9A\xA0"
INFO="\xE2\x8F\xB3"

# Log function with emojis
log() {
    local level="$1"
    local message="$2"
    local emoji="$3"
    local timestamp
    timestamp=$(date +"%Y-%m-%d %H:%M:%S")
    local colour
    case "$level" in
        "SUCCESS") colour="$GREEN" ;;
        "ERROR")   colour="$RED" ;;
        "WARNING") colour="$YELLOW" ;;
        *)         colour="$BLUE" ;;
    esac
    echo -e "${timestamp} [${colour}${level}${RESET}] ${emoji} ${message}" | tee -a "$LOGFILE"
}

# ASCII Art Header
header() {
    echo -e "\n${BLUE}${BOLD}"
    echo "==================================="
    echo " 🎨 LXC AutoScale ML Installer 🎨 "
    echo "==================================="
    echo -e "${RESET}"
    echo "Welcome to the LXC AutoScale ML installation script!"
    echo "This script will guide you through the setup process."
    echo "==================================="
    echo
}

# Check and install necessary software
check_software() {
    log "INFO" "Checking for required software..." "$INFO"

    if ! command -v python3 &> /dev/null; then
        log "ERROR" "Python3 is not installed. Please install Python3 and rerun the script." "$CROSSMARK"
        exit 1
    else
        log "INFO" "Python3 is installed." "$CHECKMARK"
    fi

    # Every third-party module imported at the top level of a deployed file must
    # appear here. tests/test_install_contract.py enforces that: python3-aiohttp
    # was missing since the async client was introduced, so the model service
    # could not start on ANY fresh install -- it logged an ERROR, the installer
    # printed "Installation process complete!" and exited 0.
    REQUIRED_SYSTEM_PACKAGES=("git" "gunicorn" "python3-flask" "python3-requests" "python3-sklearn" "python3-pandas" "python3-numpy" "python3-aiohttp" "python3-aiofiles" "python3-psutil" "python3-yaml" "python3-prometheus-client")

    for package in "${REQUIRED_SYSTEM_PACKAGES[@]}"; do
        # dpkg -l | grep -qw matched the version and description columns, and
        # matched removed-but-not-purged (rc) records as installed.
        if [[ "$(dpkg-query -W -f='${db:Status-Status}' "$package" 2>/dev/null)" == "installed" ]]; then
            log "INFO" "System package $package is already installed." "$CHECKMARK"
        else
            log "INFO" "Installing system package: $package..." "$INFO"
            if apt update && apt install -y "$package"; then
                log "INFO" "Successfully installed $package." "$CHECKMARK"
            else
                log "ERROR" "Failed to install $package." "$CROSSMARK"
                exit 1
            fi
        fi
    done
}

# Function to create a backup of specified files
backup_files() {
    local files_to_backup=(
        "/etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml"
        "/etc/lxc_autoscale_ml/lxc_autoscale_api.yaml"
        "/etc/lxc_autoscale_ml/lxc_monitor.yaml"
    )

    local timestamp
    timestamp=$(date +"%Y%m%d%H%M%S")

    log "INFO" "Creating backups..." "$INFO"
    for file in "${files_to_backup[@]}"; do
        if [[ -e "$file" ]]; then
            local backup_file="${file}_backup_${timestamp}"
            if cp "$file" "$backup_file"; then
                log "INFO" "Backed up $file to $backup_file" "$CHECKMARK"
            else
                log "ERROR" "Failed to back up $file" "$CROSSMARK"
            fi
        else
            log "WARNING" "$file does not exist, skipping." "$WARNING"
        fi
    done
}

# Function to install LXC AutoScale ML
install_lxc_autoscale_ml() {
    log "INFO" "Installing LXC AutoScale ML..." "$INFO"

    # Disable and stop services if running
    # Stop only. Disabling here meant a later failure -- a failed git clone,
    # say -- left a previously working install disabled, so it did not come
    # back after a reboot either. setup_service re-enables at the end.
    systemctl stop lxc_autoscale_ml.service lxc_autoscale_api.service lxc_monitor.service 2>/dev/null || true

    # Reload systemd
    systemctl daemon-reload

    # Create necessary directories
    mkdir -p /etc/lxc_autoscale_ml /usr/local/bin/lxc_autoscale_api /usr/local/bin/lxc_autoscale_ml
    # The configs below carry API keys.
    chmod 0750 /etc/lxc_autoscale_ml

    # Clone the repository
    REPO_URL="https://github.com/fabriziosalmi/proxmox-lxc-autoscale-ml.git"
    TEMP_DIR=$(mktemp -d)
    # Override to install a tag rather than the default branch:
    #   LXC_AUTOSCALE_REF=v1.4.0 ./install.sh
    REF="${LXC_AUTOSCALE_REF:-}"

    log "INFO" "Cloning the repository from $REPO_URL${REF:+ at $REF}..." "$INFO"
    if git clone ${REF:+--branch "$REF"} --depth 1 "$REPO_URL" "$TEMP_DIR"; then
        log "INFO" "Successfully cloned the repository." "$CHECKMARK"
    else
        log "ERROR" "Failed to clone the repository." "$CROSSMARK"
        exit 1
    fi

    # Move files to the appropriate locations
    move_files "$TEMP_DIR"

    # Clean up temporary directory
    rm -rf "$TEMP_DIR"

    # Reload systemd to recognize the new services
    systemctl daemon-reload

    # Set up services
    setup_service "lxc_autoscale_api.service"
    setup_service "lxc_monitor.service"
    setup_service "lxc_autoscale_ml.service"
}

# Install a config file without overwriting an existing one. On an upgrade the
# shipped defaults land next to the current file as <name>.yaml.new so local
# edits survive; previously every upgrade silently replaced them.
install_config() {
    local source_file="$1"
    local name
    name=$(basename "$source_file")
    local target="/etc/lxc_autoscale_ml/${name}"

    # 0600: lxc_autoscale_api.yaml holds authentication.api_keys, and the
    # model config holds the matching api.api_key. They were installed
    # world-readable into a world-readable directory.
    if [[ -e "$target" ]]; then
        install -m 0600 -o root -g root "$source_file" "${target}.new"
        rm -f "$source_file"
        log "WARNING" "${target} already exists; shipped defaults written to ${target}.new" "$WARNING"
    else
        install -m 0600 -o root -g root "$source_file" "$target"
        rm -f "$source_file"
        log "SUCCESS" "Installed ${target}" "$CHECKMARK"
    fi
}

# Function to move files to their respective directories
move_files() {
    local source_dir="$1"

    log "INFO" "Moving files to their respective directories..." "$INFO"

    mv "$source_dir/lxc_autoscale_ml/api/"*.py /usr/local/bin/lxc_autoscale_api/
    mv "$source_dir/lxc_autoscale_ml/monitor/lxc_monitor.py" /usr/local/bin/
    mv "$source_dir/lxc_autoscale_ml/model/"*.py /usr/local/bin/lxc_autoscale_ml/

    install_config "$source_dir/lxc_autoscale_ml/api/lxc_autoscale_api.yaml"
    install_config "$source_dir/lxc_autoscale_ml/monitor/lxc_monitor.yaml"
    install_config "$source_dir/lxc_autoscale_ml/model/lxc_autoscale_ml.yaml"
    mv "$source_dir/lxc_autoscale_ml/api/lxc_autoscale_api.service" /etc/systemd/system/
    mv "$source_dir/lxc_autoscale_ml/monitor/lxc_monitor.service" /etc/systemd/system/
    mv "$source_dir/lxc_autoscale_ml/model/lxc_autoscale_ml.service" /etc/systemd/system/

    chmod +x /usr/local/bin/lxc_autoscale_ml/lxc_autoscale_ml.py
    chmod +x /usr/local/bin/lxc_autoscale_api/lxc_autoscale_api.py
    chmod +x /usr/local/bin/lxc_monitor.py
}

# Helper function to set up services
setup_service() {
    local service_name="$1"
    if systemctl enable "$service_name" && systemctl start "$service_name"; then
        log "SUCCESS" "Service $service_name started successfully!" "$CHECKMARK"
    else
        # Previously this logged an error and the installer still printed
        # "Installation process complete!" and exited 0, so a missing
        # dependency looked like a successful install.
        log "ERROR" "Failed to start service $service_name." "$CROSSMARK"
        systemctl status "$service_name" --no-pager || true
        journalctl -u "$service_name" -n 30 --no-pager || true
        return 1
    fi
}

# Main script execution
if [[ ${EUID} -ne 0 ]]; then
    echo "This installer writes to /etc, /usr/local/bin and /etc/systemd/system." >&2
    echo "Re-run it as root." >&2
    exit 1
fi

header
check_software
backup_files
install_lxc_autoscale_ml
log "INFO" "Installation process complete!" "$CHECKMARK"
