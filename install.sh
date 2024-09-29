#!/bin/bash

# Log file
LOGFILE="lxc_autoscale_ml_installer.log"

# Define text styles and emojis
BOLD=$(tput bold)
RESET=$(tput sgr0)
GREEN=$(tput setaf 2)
RED=$(tput setaf 1)
YELLOW=$(tput setaf 3)
BLUE=$(tput setaf 4)
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
    echo -e "${timestamp} [${level}] ${emoji} ${message}" | tee -a "$LOGFILE"
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

    REQUIRED_SYSTEM_PACKAGES=("git" "python3-flask" "python3-requests" "python3-sklearn" "python3-pandas" "python3-numpy" "python3-aiofiles")

    for package in "${REQUIRED_SYSTEM_PACKAGES[@]}"; do
        if dpkg -l | grep -qw "$package"; then
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
    systemctl disable lxc_autoscale_ml.service lxc_autoscale_api.service lxc_monitor.service 2>/dev/null
    systemctl stop lxc_autoscale_ml.service lxc_autoscale_api.service lxc_monitor.service 2>/dev/null

    # Reload systemd
    systemctl daemon-reload

    # Create necessary directories
    mkdir -p /etc/lxc_autoscale_ml /usr/local/bin/lxc_autoscale_api /usr/local/bin/lxc_autoscale_ml

    # Clone the repository
    REPO_URL="https://github.com/fabriziosalmi/proxmox-lxc-autoscale-ml.git"
    TEMP_DIR=$(mktemp -d)

    log "INFO" "Cloning the repository from $REPO_URL..." "$INFO"
    if git clone "$REPO_URL" "$TEMP_DIR"; then
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

# Function to move files to their respective directories
move_files() {
    local source_dir="$1"

    log "INFO" "Moving files to their respective directories..." "$INFO"

    mv "$source_dir/lxc_autoscale_ml/api/"*.py /usr/local/bin/lxc_autoscale_api/
    mv "$source_dir/lxc_autoscale_ml/api/lxc_autoscale_api.yaml" /etc/lxc_autoscale_ml/
    mv "$source_dir/lxc_autoscale_ml/monitor/lxc_monitor.py" /usr/local/bin/
    mv "$source_dir/lxc_autoscale_ml/monitor/lxc_monitor.yaml" /etc/lxc_autoscale_ml/
    mv "$source_dir/lxc_autoscale_ml/model/"*.py /usr/local/bin/lxc_autoscale_ml/
    mv "$source_dir/lxc_autoscale_ml/model/lxc_autoscale_ml.yaml" /etc/lxc_autoscale_ml/
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
        log "INFO" "${CHECKMARK} Service $service_name started successfully!" "$CHECKMARK"
    else
        log "ERROR" "${CROSSMARK} Failed to start service $service_name." "$CROSSMARK"
        systemctl status "$service_name" --no-pager
    fi
}

# Main script execution
header
check_software
backup_files
install_lxc_autoscale_ml
log "INFO" "Installation process complete!" "$CHECKMARK"
