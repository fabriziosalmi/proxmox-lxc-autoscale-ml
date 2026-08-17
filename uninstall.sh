#!/bin/bash
#
# LXC AutoScale ML uninstaller.

set -euo pipefail

# Log file for uninstallation
LOGFILE="lxc_autoscale_ml_uninstaller.log"

# Define text styles and emojis
BOLD=$(tput bold)
RESET=$(tput sgr0)
GREEN=$(tput setaf 2)
RED=$(tput setaf 1)
YELLOW=$(tput setaf 3)
BLUE=$(tput setaf 4)
CYAN=$(tput setaf 6)
CHECKMARK="\xE2\x9C\x85"  # ✔️
CROSSMARK="\xE2\x9D\x8C"  # ❌
WARNING="\xE2\x9A\xA0"    # ⚠️
INFO="\xE2\x84\xB9"        # ℹ️
SKIP="\xF0\x9F\x94\x8F"   # ⏭️
FEEDBACK="\xF0\x9F\x93\x9D" # 📝

# Log function with emojis
log() {
    local level="$1"
    local message="$2"
    local emoji="$3"
    local timestamp
    timestamp=$(date +"%Y-%m-%d %H:%M:%S")
    case $level in
        "INFO")
            echo -e "${timestamp} [${CYAN}${level}${RESET}] ${emoji} ${message}" | tee -a "$LOGFILE"
            ;;
        "ERROR")
            echo -e "${timestamp} [${RED}${level}${RESET}] ${emoji} ${message}" | tee -a "$LOGFILE"
            ;;
        "SUCCESS")
            echo -e "${timestamp} [${GREEN}${level}${RESET}] ${emoji} ${message}" | tee -a "$LOGFILE"
            ;;
        "WARNING")
            echo -e "${timestamp} [${YELLOW}${level}${RESET}] ${emoji} ${message}" | tee -a "$LOGFILE"
            ;;
    esac
}

log "INFO" "Starting LXC AutoScale ML uninstallation..." "$INFO"

# Keep a copy of the configuration before removing it. The uninstaller deletes
# /etc/lxc_autoscale_ml/*.yaml, which is where any local tuning lives; without
# this, reinstalling means redoing all of it from memory.
backup_configs() {
    local timestamp
    timestamp=$(date +"%Y%m%d%H%M%S")
    local backup_dir="/root/lxc_autoscale_ml_config_backup_${timestamp}"
    local found=0

    for file in /etc/lxc_autoscale_ml/*.yaml; do
        [[ -e "$file" ]] || continue
        if [[ $found -eq 0 ]]; then
            mkdir -p "$backup_dir"
            found=1
        fi
        cp "$file" "$backup_dir/"
    done

    if [[ $found -eq 1 ]]; then
        log "SUCCESS" "Configuration backed up to ${backup_dir}" "$CHECKMARK"
    else
        log "WARNING" " No configuration files found to back up." "$SKIP"
    fi
}

backup_configs

# Function to stop and disable a service
uninstall_service() {
    local service_name="$1"
    log "INFO" "Stopping and disabling the ${service_name} service..." "$INFO"

    if systemctl is-active --quiet "$service_name" 2>/dev/null; then
        if systemctl stop "$service_name"; then
            log "SUCCESS" "Successfully stopped ${service_name}." "$CHECKMARK"
        else
            log "ERROR" "Failed to stop ${service_name}." "$CROSSMARK"
        fi
    else
        log "WARNING" " ${service_name} is not running or does not exist." "$WARNING"
    fi

    if systemctl is-enabled --quiet "$service_name" 2>/dev/null; then
        if systemctl disable "$service_name"; then
            log "SUCCESS" "Successfully disabled ${service_name}." "$CHECKMARK"
        else
            log "ERROR" "Failed to disable ${service_name}." "$CROSSMARK"
        fi
    else
        log "WARNING" " ${service_name} is not enabled or does not exist." "$WARNING"
    fi
}

# Function to remove files and directories
remove_files() {
    local files=("$@")
    for file in "${files[@]}"; do
        if [[ -e "$file" ]]; then
            log "INFO" "Removing ${file} ..." "$INFO"
            if rm -rf "$file"; then
                log "SUCCESS" "Successfully removed ${file}." "$CHECKMARK"
            else
                log "ERROR" "Failed to remove ${file}." "$CROSSMARK"
            fi
        else
            log "WARNING" " ${file} does not exist, skipping." "$SKIP"
        fi
    done
}

# Uninstall LXC AutoScale API
log "INFO" "Uninstalling LXC AutoScale API..." "$INFO"
uninstall_service "lxc_autoscale_api.service"
remove_files "/usr/local/bin/lxc_autoscale_api" "/etc/systemd/system/lxc_autoscale_api.service" "/etc/lxc_autoscale_ml/lxc_autoscale_api.yaml"

# Uninstall LXC AutoScale ML
log "INFO" "Uninstalling LXC AutoScale ML..." "$INFO"
uninstall_service "lxc_autoscale_ml.service"
remove_files "/usr/local/bin/lxc_autoscale_ml" "/etc/systemd/system/lxc_autoscale_ml.service" "/etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml"

# Uninstall LXC Monitor
log "INFO" "Uninstalling LXC Monitor..." "$INFO"
uninstall_service "lxc_monitor.service"
remove_files "/usr/local/bin/lxc_monitor.py" "/etc/systemd/system/lxc_monitor.service" "/etc/lxc_autoscale_ml/lxc_monitor.yaml"

# Cleanup configuration directory
log "INFO" "Cleaning up shared configuration directory if empty..." "$INFO"
if [ -d "/etc/lxc_autoscale_ml" ] && [ ! "$(ls -A /etc/lxc_autoscale_ml)" ]; then
    rmdir /etc/lxc_autoscale_ml
    log "SUCCESS" "Successfully removed empty directory /etc/lxc_autoscale_ml." "$CHECKMARK"
else
    log "WARNING" " Directory /etc/lxc_autoscale_ml is not empty or does not exist, skipping." "$SKIP"
fi

# Reload systemd to reflect changes
log "INFO" "Reloading systemd daemon to reflect changes..." "$INFO"
systemctl daemon-reload || true

# Final message
log "SUCCESS" "LXC AutoScale ML uninstallation complete!" "$CHECKMARK"
log "INFO" "We appreciate your feedback! If you encountered any issues or have suggestions, please open an issue on our GitHub repository:" "$FEEDBACK"
echo -e "${BLUE}${BOLD}👉  https://github.com/fabriziosalmi/proxmox-lxc-autoscale-ml/issues ${RESET}"
echo -e "${BLUE}${BOLD}✉️   You can also provide feedback via email: fabrizio.salmi@gmail.com${RESET}"
echo -e "${GREEN}${BOLD}Thank you for using LXC AutoScale ML! 🙏${RESET}"
