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
CHECKMARK="\xE2\x9C\x85"  # ✔️ Success
CROSSMARK="\xE2\x9D\x8C"  # ❌ Error
WARNING="\xE2\x9A\xA0"    # ⚠️ Warning
INFO="\xE2\x8F\xB3"       # ⏳ Info

# Log function with emojis
log() {
    local level="$1"
    local message="$2"
    local emoji="$3"
    local timestamp
    timestamp=$(date +"%Y-%m-%d %H:%M:%S")
    case $level in
        "INFO")
            echo -e "${timestamp} [${GREEN}${level}${RESET}] ${emoji} ${message}" | tee -a "$LOGFILE"
            ;;
        "ERROR")
            echo -e "${timestamp} [${RED}${level}${RESET}] ${emoji} ${message}" | tee -a "$LOGFILE"
            ;;
        "WARNING")
            echo -e "${timestamp} [${YELLOW}${level}${RESET}] ${emoji} ${message}" | tee -a "$LOGFILE"
            ;;
    esac
}

# ASCII Art Header
header() {
    echo -e "\n${BLUE}${BOLD}🎨 LXC AutoScale ML Installer${RESET}"
    echo "============================="
    echo "Welcome to the LXC AutoScale ML installation script!"
    echo "============================="
    echo
}

# Check and install necessary software
check_software() {
    log "INFO" "Checking for required software..." "$INFO"

    # Check for Python3
    if ! command -v python3 &> /dev/null; then
        log "ERROR" "Python3 is not installed. Please install Python3 and rerun the script." "$CROSSMARK"
        exit 1
    else
        log "INFO" "Python3 is installed." "$CHECKMARK"
    fi

    # Install required system packages
    REQUIRED_SYSTEM_PACKAGES=("git" "python3-flask" "python3-requests" "python3-sklearn" "python3-pandas" "python3-numpy")

    for package in "${REQUIRED_SYSTEM_PACKAGES[@]}"; do
        if dpkg -l | grep -qw "$package"; then
            log "INFO" "System package $package is already installed." "$CHECKMARK"
        else
            log "INFO" "Installing system package: $package..." "$INFO"
            if ! apt update && apt install -y "$package"; then
                log "ERROR" "Failed to install $package." "$CROSSMARK"
                exit 1
            else
                log "INFO" "Successfully installed $package." "$CHECKMARK"
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

    # Disable and stop lxc_autoscale if running. Don't use both at the same time
    systemctl disable lxc_autoscale 2>/dev/null
    systemctl stop lxc_autoscale 2>/dev/null

    # Stop lxc_autoscale_ml if running
    systemctl stop lxc_autoscale_ml 2>/dev/null

    # Reload systemd
    systemctl daemon-reload

    # Create necessary directories
    mkdir -p /etc/lxc_autoscale_ml /usr/local/bin/lxc_autoscale_api /usr/local/bin/lxc_autoscale_ml

    # Create empty __init__.py files to treat directories as Python packages
    touch /usr/local/bin/lxc_autoscale_ml/__init__.py /usr/local/bin/lxc_autoscale_api/__init__.py

    # Helper function to download files
    download_file() {
        local url="$1"
        local destination="$2"
        if curl -sSL -o "$destination" "$url"; then
            log "INFO" "Downloaded $url to $destination" "$CHECKMARK"
        else
            log "ERROR" "Failed to download $url" "$CROSSMARK"
            exit 1
        fi
    }

    # Helper function to set up services
    setup_service() {
        local service_name="$1"
        if systemctl enable "$service_name" && systemctl start "$service_name"; then
            log "INFO" "${CHECKMARK} Service $service_name started successfully!" "$CHECKMARK"
        else
            log "ERROR" "${CROSSMARK} Failed to start service $service_name." "$CROSSMARK"
        fi
    }

    # Download and install API application files
    BASE_URL="https://raw.githubusercontent.com/fabriziosalmi/proxmox-lxc-autoscale-ml/main"
    API_FILES=(
        "api/lxc_autoscale_api.py"
        "api/cloning_management.py"
        "api/config.py"
        "api/error_handling.py"
        "api/health_check.py"
        "api/lxc_management.py"
        "api/resource_checking.py"
        "api/scaling.py"
        "api/snapshot_management.py"
        "api/utils.py"
    )

    for file in "${API_FILES[@]}"; do
        download_file "$BASE_URL/$file" "/usr/local/bin/lxc_autoscale_api/$(basename $file)"
    done

    # Download and install the API configuration file
    download_file "$BASE_URL/api/lxc_autoscale_api.yaml" "/etc/lxc_autoscale_ml/lxc_autoscale_api.yaml"

    # Download and install the monitor application files
    download_file "$BASE_URL/monitor/lxc_monitor.py" "/usr/local/bin/lxc_monitor.py"
    download_file "$BASE_URL/api/lxc_autoscale_api.yaml" "/etc/lxc_autoscale_ml/lxc_monitor.yaml"

    # Download and install model application files
    MODEL_FILES=(
        "model/config_manager.py"
        "model/data_manager.py"
        "model/lock_manager.py"
        "model/logger.py"
        "model/model.py"
        "model/scaling.py"
        "model/signal_handler.py"
        "model/lxc_autoscale_ml.py"
    )

    for file in "${MODEL_FILES[@]}"; do
        download_file "$BASE_URL/$file" "/usr/local/bin/lxc_autoscale_ml/$(basename $file)"
    done

    # Download and install the model configuration file
    download_file "$BASE_URL/model/lxc_autoscale_ml.yaml" "/etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml"

    # Corrected URLs for the service files
    SERVICE_FILES=(
        "lxc_autoscale_ml/api/lxc_autoscale_api.service"
        "lxc_autoscale_ml/model/lxc_autoscale_ml.service"
        "lxc_autoscale_ml/monitor/lxc_monitor.service"
    )

    for file in "${SERVICE_FILES[@]}"; do
        download_file "$BASE_URL/$file" "/etc/systemd/system/$(basename $file)"
    done

    # Make the main scripts executable
    chmod +x /usr/local/bin/lxc_autoscale_ml/lxc_autoscale_ml.py
    chmod +x /usr/local/bin/lxc_autoscale_api/lxc_autoscale_api.py
    chmod +x /usr/local/bin/lxc_monitor.py

    # Reload systemd to recognize the new services
    systemctl daemon-reload

    # Set up services
    setup_service "lxc_autoscale_api.service"
    setup_service "lxc_monitor.service"
    setup_service "lxc_autoscale_ml.service"

    # Show status for all installed services
    systemctl status lxc_monitor.service --no-pager
    systemctl status lxc_autoscale_api.service --no-pager
    systemctl status lxc_autoscale_ml.service --no-pager
}

# Main script execution
header
check_software
backup_files
install_lxc_autoscale_ml
log "INFO" "Installation process complete!" "$CHECKMARK"
