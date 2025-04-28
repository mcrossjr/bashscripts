#!/bin/bash
# Password update script for multiple servers via SSH
# This script reads server IPs from a file and updates a user's password

# Colors for better readability
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
SSH_PORT=22
SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=5"
SERVER_LIST="servers.txt"

# Print header
echo -e "${BLUE}=========================================${NC}"
echo -e "${BLUE}   Multi-Server Password Update Script   ${NC}"
echo -e "${BLUE}=========================================${NC}"

# Check if servers file exists
if [[ ! -f "$SERVER_LIST" ]]; then
    echo -e "${YELLOW}Servers file $SERVER_LIST not found.${NC}"
    read -p "Would you like to create it now? (y/n): " create_file
    if [[ "$create_file" == "y" || "$create_file" == "Y" ]]; then
        touch "$SERVER_LIST"
        echo -e "${GREEN}Created $SERVER_LIST. Please add server IPs, one per line.${NC}"
        echo -e "Format: 192.168.1.100"
        echo -e "        10.0.0.5"
        exit 0
    else
        echo -e "${RED}Error: Server list file required to continue.${NC}"
        exit 1
    fi
fi

# Check if file is empty
if [[ ! -s "$SERVER_LIST" ]]; then
    echo -e "${RED}Error: $SERVER_LIST is empty. Please add server IPs, one per line.${NC}"
    exit 1
fi

# Get the SSH username
read -p "SSH Username (for login): " SSH_USER
if [[ -z "$SSH_USER" ]]; then
    echo -e "${RED}Error: SSH username is required.${NC}"
    exit 1
fi

# Get SSH password securely
read -s -p "SSH Password: " SSH_PASS
echo
if [[ -z "$SSH_PASS" ]]; then
    echo -e "${RED}Error: SSH password is required.${NC}"
    exit 1
fi

# Get the target username whose password will be changed
read -p "Username to change password for: " TARGET_USER
if [[ -z "$TARGET_USER" ]]; then
    echo -e "${RED}Error: Target username is required.${NC}"
    exit 1
fi

# Get the new password securely
read -s -p "New password for $TARGET_USER: " NEW_PASS
echo
if [[ -z "$NEW_PASS" ]]; then
    echo -e "${RED}Error: New password is required.${NC}"
    exit 1
fi

# Confirm password
read -s -p "Confirm new password: " CONFIRM_PASS
echo
if [[ "$NEW_PASS" != "$CONFIRM_PASS" ]]; then
    echo -e "${RED}Error: Passwords do not match.${NC}"
    exit 1
fi

# Check for SSH key option
read -p "Use SSH key instead of password? (y/n, default: n): " USE_KEY
if [[ "$USE_KEY" == "y" || "$USE_KEY" == "Y" ]]; then
    read -p "Path to SSH private key: " SSH_KEY
    if [[ ! -f "$SSH_KEY" ]]; then
        echo -e "${RED}Error: SSH key file not found.${NC}"
        exit 1
    fi
    SSH_AUTH="-i $SSH_KEY"
else
    # Using sshpass for password authentication
    if ! command -v sshpass &> /dev/null; then
        echo -e "${RED}Error: sshpass is not installed. Install it with:${NC}"
        echo -e "Ubuntu/Debian: ${YELLOW}sudo apt-get install sshpass${NC}"
        echo -e "CentOS/RHEL:   ${YELLOW}sudo yum install sshpass${NC}"
        echo -e "MacOS:         ${YELLOW}brew install hudochenkov/sshpass/sshpass${NC}"
        exit 1
    fi
    SSH_AUTH="sshpass -p $SSH_PASS"
fi

# Custom SSH port option
read -p "SSH Port (default: 22): " PORT_INPUT
if [[ ! -z "$PORT_INPUT" ]]; then
    SSH_PORT=$PORT_INPUT
fi

# Count servers
SERVER_COUNT=$(wc -l < "$SERVER_LIST")
echo -e "\n${BLUE}Ready to update password for user ${YELLOW}$TARGET_USER${BLUE} on ${YELLOW}$SERVER_COUNT${BLUE} servers.${NC}"

# Confirm before proceeding
read -p "Proceed with password update? (y/n): " CONFIRM
if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
    echo -e "${YELLOW}Operation cancelled.${NC}"
    exit 0
fi

# Function to update password on a server
update_password() {
    local server=$1
    echo -e "\n${BLUE}Processing server: ${YELLOW}$server${NC}"
    
    # Create password change command - uses chpasswd which is more secure than echo to passwd
    PASSWORD_COMMAND="echo '$TARGET_USER:$NEW_PASS' | sudo -S chpasswd"
    
    # Execute command via SSH
    if [[ "$USE_KEY" == "y" || "$USE_KEY" == "Y" ]]; then
        # Using SSH key
        ssh $SSH_OPTS -p $SSH_PORT -i "$SSH_KEY" $SSH_USER@$server "$PASSWORD_COMMAND" 2>/tmp/ssh_error
    else
        # Using password
        $SSH_AUTH ssh $SSH_OPTS -p $SSH_PORT $SSH_USER@$server "$PASSWORD_COMMAND" 2>/tmp/ssh_error
    fi
    
    # Check result
    SSH_RESULT=$?
    if [[ $SSH_RESULT -eq 0 ]]; then
        echo -e "${GREEN}✓ Password successfully updated on $server${NC}"
        return 0
    else
        ERROR=$(cat /tmp/ssh_error)
        echo -e "${RED}✗ Failed to update password on $server${NC}"
        echo -e "${RED}  Error: $ERROR${NC}"
        return 1
    fi
}

# Process all servers
echo -e "\n${BLUE}Starting password updates...${NC}"

SUCCESS_COUNT=0
FAILED_COUNT=0
FAILED_SERVERS=""

# Loop through each server
while IFS= read -r server || [[ -n "$server" ]]; do
    # Skip empty lines and comments
    [[ -z "$server" || "$server" =~ ^# ]] && continue
    
    # Update password on the server
    if update_password "$server"; then
        ((SUCCESS_COUNT++))
    else
        ((FAILED_COUNT++))
        FAILED_SERVERS="$FAILED_SERVERS\n  - $server"
    fi
done < "$SERVER_LIST"

# Print summary
echo -e "\n${BLUE}========== SUMMARY ==========${NC}"
echo -e "${GREEN}Successfully updated: $SUCCESS_COUNT${NC}"
echo -e "${RED}Failed: $FAILED_COUNT${NC}"

if [[ $FAILED_COUNT -gt 0 ]]; then
    echo -e "${RED}Failed servers:$FAILED_SERVERS${NC}"
fi

echo -e "\n${BLUE}Password update completed.${NC}"

# Clean up
rm -f /tmp/ssh_error

exit 0
