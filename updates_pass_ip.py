#!/usr/bin/env python3
"""
Script to update user passwords across multiple EC2 instances using AWS SSM
Supports using private IP addresses to identify instances
Requires boto3: pip install boto3

run this in the aws cli
"""

import boto3
import getpass
import time
import sys
from botocore.exceptions import ClientError


def get_instance_ids_from_ips(private_ips):
    """
    Convert private IP addresses to instance IDs
    
    Args:
        private_ips: List of private IP addresses
        
    Returns:
        Dictionary mapping private IPs to instance IDs
    """
    ec2 = boto3.client('ec2')
    ip_to_instance = {}
    
    try:
        response = ec2.describe_instances(
            Filters=[
                {'Name': 'private-ip-address', 'Values': private_ips},
                {'Name': 'instance-state-name', 'Values': ['running']}
            ]
        )
        
        for reservation in response['Reservations']:
            for instance in reservation['Instances']:
                private_ip = instance.get('PrivateIpAddress')
                if private_ip and private_ip in private_ips:
                    ip_to_instance[private_ip] = instance['InstanceId']
        
        return ip_to_instance
    
    except ClientError as e:
        print(f"Error fetching instances: {e}")
        return {}


def get_instance_info():
    """
    Get instance information (either from IPs or IDs)
    
    Returns:
        tuple: (instance_ids, display_info)
    """
    print("\nHow would you like to select EC2 instances?")
    print("1. From a file (ip_addresses.txt with private IPs)")
    print("2. From a file (instance_ids.txt with instance IDs)")
    print("3. By tag (e.g., Environment=Production)")
    print("4. Specify private IP addresses directly")
    print("5. Specify instance IDs directly")
    
    choice = input("Enter your choice (1-5): ")
    
    instance_ids = []
    display_info = {}  # For displaying user-friendly information
    
    if choice == "1":  # From file with private IPs
        try:
            with open("ip_addresses.txt", "r") as f:
                private_ips = [line.strip() for line in f if line.strip()]
            
            if not private_ips:
                print("Error: No IP addresses found in ip_addresses.txt")
                sys.exit(1)
            
            ip_to_instance = get_instance_ids_from_ips(private_ips)
            
            if not ip_to_instance:
                print("Error: Could not find any running instances with the specified IP addresses")
                sys.exit(1)
            
            instance_ids = list(ip_to_instance.values())
            display_info = {instance_id: f"IP: {ip}" for ip, instance_id in ip_to_instance.items()}
            
            # Report any IPs that weren't found
            not_found = [ip for ip in private_ips if ip not in ip_to_instance]
            if not_found:
                print(f"\nWarning: Could not find instances for {len(not_found)} IP addresses:")
                for ip in not_found:
                    print(f"  - {ip}")
        
        except FileNotFoundError:
            print("Error: ip_addresses.txt file not found")
            print("Please create a file named 'ip_addresses.txt' with one IP address per line.")
            sys.exit(1)
    
    elif choice == "2":  # From file with instance IDs
        try:
            with open("instance_ids.txt", "r") as f:
                instance_ids = [line.strip() for line in f if line.strip()]
            
            if not instance_ids:
                print("Error: No instance IDs found in instance_ids.txt")
                sys.exit(1)
            
            display_info = {instance_id: f"ID: {instance_id}" for instance_id in instance_ids}
        
        except FileNotFoundError:
            print("Error: instance_ids.txt file not found")
            print("Please create a file named 'instance_ids.txt' with one instance ID per line.")
            sys.exit(1)
    
    elif choice == "3":  # By tag
        tags = []
        while True:
            key = input("Enter tag key (or press Enter to finish): ")
            if not key:
                break
            value = input(f"Enter value for tag '{key}': ")
            tags.append({"Key": key, "Value": value})
        
        if not tags:
            print("No tags specified. Exiting.")
            sys.exit(1)
        
        ec2 = boto3.client('ec2')
        filters = [{'Name': f"tag:{tag['Key']}", 'Values': [tag['Value']]} for tag in tags]
        
        try:
            response = ec2.describe_instances(Filters=filters)
            for reservation in response['Reservations']:
                for instance in reservation['Instances']:
                    if instance['State']['Name'] == 'running':
                        instance_id = instance['InstanceId']
                        instance_ids.append(instance_id)
                        
                        # Get name tag if exists
                        name = "Unnamed"
                        for tag in instance.get('Tags', []):
                            if tag['Key'] == 'Name':
                                name = tag['Value']
                                break
                        
                        private_ip = instance.get('PrivateIpAddress', 'No IP')
                        display_info[instance_id] = f"{name} ({private_ip})"
        
        except ClientError as e:
            print(f"Error fetching instances: {e}")
            sys.exit(1)
    
    elif choice == "4":  # Specify IPs directly
        ips_input = input("Enter private IP addresses separated by commas: ")
        private_ips = [ip.strip() for ip in ips_input.split(",") if ip.strip()]
        
        if not private_ips:
            print("No IP addresses specified. Exiting.")
            sys.exit(1)
        
        ip_to_instance = get_instance_ids_from_ips(private_ips)
        
        if not ip_to_instance:
            print("Error: Could not find any running instances with the specified IP addresses")
            sys.exit(1)
        
        instance_ids = list(ip_to_instance.values())
        display_info = {instance_id: f"IP: {ip}" for ip, instance_id in ip_to_instance.items()}
        
        # Report any IPs that weren't found
        not_found = [ip for ip in private_ips if ip not in ip_to_instance]
        if not_found:
            print(f"\nWarning: Could not find instances for {len(not_found)} IP addresses:")
            for ip in not_found:
                print(f"  - {ip}")
    
    elif choice == "5":  # Specify instance IDs directly
        ids_input = input("Enter instance IDs separated by commas: ")
        instance_ids = [id.strip() for id in ids_input.split(",") if id.strip()]
        
        if not instance_ids:
            print("No instance IDs specified. Exiting.")
            sys.exit(1)
        
        display_info = {instance_id: f"ID: {instance_id}" for instance_id in instance_ids}
    
    else:
        print("Invalid choice. Exiting.")
        sys.exit(1)
    
    if not instance_ids:
        print("No instances found or specified. Exiting.")
        sys.exit(1)
    
    return instance_ids, display_info


def verify_ssm_availability(instance_ids):
    """
    Verify which instances are available via SSM
    
    Args:
        instance_ids: List of instance IDs to check
        
    Returns:
        tuple: (available_instances, unavailable_instances)
    """
    ssm = boto3.client('ssm')
    
    try:
        paginator = ssm.get_paginator('describe_instance_information')
        available_instances = set()
        
        for page in paginator.paginate():
            for instance in page['InstanceInformationList']:
                if instance['InstanceId'] in instance_ids:
                    available_instances.add(instance['InstanceId'])
        
        unavailable_instances = [id for id in instance_ids if id not in available_instances]
        return list(available_instances), unavailable_instances
    
    except ClientError as e:
        print(f"Error checking SSM availability: {e}")
        return [], instance_ids


def update_password(instance_ids, username, new_password):
    """
    Update password for a user across multiple instances using SSM
    
    Args:
        instance_ids: List of EC2 instance IDs
        username: Username to update
        new_password: New password to set
        
    Returns:
        Dictionary with results
    """
    if not instance_ids:
        return {"success": False, "message": "No instances provided"}
    
    ssm = boto3.client('ssm')
    
    # Create a secure password command
    # We're using the chpasswd command which takes input in the format username:password
    command = f"echo '{username}:{new_password}' | sudo chpasswd"
    
    try:
        # Send the command to all instances
        response = ssm.send_command(
            InstanceIds=instance_ids,
            DocumentName="AWS-RunShellScript",
            Parameters={'commands': [command]},
            Comment=f"Update password for user {username}"
        )
        
        command_id = response['Command']['CommandId']
        print(f"Command sent successfully. Command ID: {command_id}")
        
        # Wait for command completion
        results = {}
        for instance_id in instance_ids:
            results[instance_id] = {"status": "Pending", "message": ""}
        
        # Poll for command completion
        all_complete = False
        retries = 0
        max_retries = 30  # 5 minutes max with 10 second intervals
        
        print("\nWaiting for command completion...")
        spinner = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        spinner_idx = 0
        
        while not all_complete and retries < max_retries:
            time.sleep(10)
            retries += 1
            all_complete = True
            
            # Simple spinner animation
            spinner_idx = (spinner_idx + 1) % len(spinner)
            print(f"\r{spinner[spinner_idx]} Checking status... {retries}/{max_retries}", end="")
            
            for instance_id in instance_ids:
                if results[instance_id]["status"] in ["Pending", "InProgress"]:
                    try:
                        result = ssm.get_command_invocation(
                            CommandId=command_id,
                            InstanceId=instance_id
                        )
                        
                        status = result['Status']
                        results[instance_id]["status"] = status
                        
                        if status == "Success":
                            results[instance_id]["message"] = "Password updated successfully"
                        elif status == "Failed":
                            results[instance_id]["message"] = f"Failed: {result.get('StandardErrorContent', 'Unknown error')}"
                        elif status in ["Pending", "InProgress"]:
                            all_complete = False
                        else:
                            results[instance_id]["message"] = f"Status: {status}"
                    
                    except ClientError as e:
                        if "InvalidInstanceId" in str(e):
                            results[instance_id]["status"] = "Failed"
                            results[instance_id]["message"] = "Instance not found or not configured for SSM"
                        else:
                            results[instance_id]["status"] = "Error"
                            results[instance_id]["message"] = str(e)
        
        print("\r" + " " * 50, end="")  # Clear the spinner line
        print("\rCommand execution completed.")
        return {"success": True, "results": results}
    
    except ClientError as e:
        return {"success": False, "message": f"Error sending command: {str(e)}"}


def main():
    """Main function to update passwords across instances"""
    print("AWS SSM Password Update Tool")
    print("===========================")
    
    # Get AWS region if not using default
    region = input("\nAWS Region (press Enter for default): ")
    if region:
        boto3.setup_default_session(region_name=region)
    
    # Get instance information
    instance_ids, display_info = get_instance_info()
    
    # Verify SSM availability
    print("\nVerifying SSM agent availability...")
    available_instances, unavailable_instances = verify_ssm_availability(instance_ids)
    
    if not available_instances:
        print("Error: None of the specified instances are available through SSM.")
        print("Please check that:")
        print("1. The SSM Agent is installed and running")
        print("2. The instances have proper IAM roles with SSM permissions")
        print("3. The instances have network connectivity to the SSM service")
        sys.exit(1)
    
    if unavailable_instances:
        print(f"\nWarning: {len(unavailable_instances)} instances are not available through SSM:")
        for instance_id in unavailable_instances:
            print(f"  - {display_info.get(instance_id, instance_id)}")
        
        proceed = input("\nDo you want to continue with the available instances? (y/n): ")
        if proceed.lower() != 'y':
            print("Operation cancelled.")
            sys.exit(0)
    
    # Display available instances
    print(f"\nReady to update password on {len(available_instances)} instances:")
    for instance_id in available_instances:
        print(f"  - {display_info.get(instance_id, instance_id)}")
    
    # Get target username and new password
    username = input("\nUsername to change password for: ")
    new_password = getpass.getpass("New password: ")
    confirm_password = getpass.getpass("Confirm new password: ")
    
    if new_password != confirm_password:
        print("Error: Passwords do not match")
        sys.exit(1)
    
    # Confirm before proceeding
    confirm = input(f"\nUpdate password for user '{username}' on {len(available_instances)} instances? (y/n): ")
    if confirm.lower() != 'y':
        print("Operation cancelled.")
        sys.exit(0)
    
    # Execute password update
    print("\nUpdating passwords...")
    result = update_password(available_instances, username, new_password)
    
    if not result["success"]:
        print(f"Error: {result['message']}")
        sys.exit(1)
    
    # Print results
    print("\nPassword Update Results:")
    print("=======================")
    
    success_count = sum(1 for instance_id, data in result["results"].items() 
                        if data["status"] == "Success")
    
    print(f"Successfully updated: {success_count}/{len(available_instances)}")
    print(f"Failed: {len(available_instances) - success_count}/{len(available_instances)}")
    
    if len(available_instances) - success_count > 0:
        print("\nInstances with errors:")
        for instance_id, data in result["results"].items():
            if data["status"] != "Success":
                print(f"  - {display_info.get(instance_id, instance_id)}: {data['status']} - {data['message']}")


if __name__ == "__main__":
    main()
