#!/usr/bin/env python3
"""
Script to SSH into multiple servers and update a user's password.
Requires the paramiko library: pip install paramiko
"""

import paramiko
import getpass
import sys
import time
from typing import List, Tuple


def update_password(
    hostname: str,
    port: int,
    ssh_username: str,
    ssh_password: str,
    target_username: str,
    new_password: str,
) -> Tuple[bool, str]:
    """
    SSH into a server and update a user's password.
    
    Args:
        hostname: The server hostname or IP address
        port: SSH port
        ssh_username: Username for SSH login
        ssh_password: Password for SSH login
        target_username: User whose password will be changed
        new_password: New password to set
        
    Returns:
        Tuple of (success_boolean, message)
    """
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        # Connect to the server
        print(f"Connecting to {hostname}:{port}...")
        client.connect(hostname, port=port, username=ssh_username, password=ssh_password)
        
        # Prepare the password change command
        # The echo command pipes the password to passwd's stdin
        command = f"echo '{target_username}:{new_password}' | sudo chpasswd"
        
        # Execute the command
        print(f"Changing password for user '{target_username}' on {hostname}...")
        stdin, stdout, stderr = client.exec_command(command)
        
        # Wait for the command to complete
        exit_status = stdout.channel.recv_exit_status()
        
        if exit_status == 0:
            return True, f"Password updated successfully for {target_username} on {hostname}"
        else:
            error = stderr.read().decode().strip()
            return False, f"Failed to update password on {hostname}: {error}"
    
    except Exception as e:
        return False, f"Error connecting to {hostname}: {str(e)}"
    
    finally:
        client.close()


def main():
    """Main function to execute the password update across multiple servers."""
    
    # Get the list of servers from a file
    try:
        with open("servers.txt", "r") as f:
            servers = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print("Error: servers.txt file not found.")
        print("Please create a file named 'servers.txt' with one IP address or hostname per line.")
        sys.exit(1)
    
    if not servers:
        print("Error: No servers found in servers.txt")
        sys.exit(1)
    
    # Get SSH credentials
    ssh_username = input("SSH Username: ")
    ssh_password = getpass.getpass("SSH Password: ")
    
    # Get the target user and new password
    target_username = input("Username to change password for: ")
    new_password = getpass.getpass("New password: ")
    confirm_password = getpass.getpass("Confirm new password: ")
    
    if new_password != confirm_password:
        print("Error: Passwords do not match")
        sys.exit(1)
    
    # SSH port - default is 22
    ssh_port = int(input("SSH Port (default 22): ") or 22)
    
    # Confirm before proceeding
    print("\nReady to update password for the following servers:")
    for server in servers:
        print(f"  - {server}")
    
    confirm = input(f"\nUpdate password for user '{target_username}' on {len(servers)} servers? (y/n): ")
    if confirm.lower() != 'y':
        print("Operation cancelled.")
        sys.exit(0)
    
    # Update password on each server
    results = []
    for hostname in servers:
        success, message = update_password(
            hostname, 
            ssh_port, 
            ssh_username, 
            ssh_password,
            target_username, 
            new_password
        )
        results.append((hostname, success, message))
        print(message)
        # Small delay between connections to avoid overwhelming network
        time.sleep(1)
    
    # Print summary
    print("\nPassword Update Summary:")
    print("-----------------------")
    success_count = sum(1 for _, success, _ in results if success)
    print(f"Successful: {success_count}/{len(servers)}")
    print(f"Failed: {len(servers) - success_count}/{len(servers)}")
    
    if len(servers) - success_count > 0:
        print("\nServers with errors:")
        for hostname, success, message in results:
            if not success:
                print(f"  - {hostname}: {message}")


if __name__ == "__main__":
    main()
