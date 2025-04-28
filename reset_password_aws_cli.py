#!/usr/bin/env python3
"""
Script to update user passwords across multiple EC2 instances using AWS SSM
Requires boto3: pip install boto3
"""

import boto3
import getpass
import time
import sys
from botocore.exceptions import ClientError


def get_instance_ids(tags=None, instance_ids=None):
    """
    Get instance IDs based on tags or from a provided list
    
    Args:
        tags: List of tag dictionaries [{'Key': 'Environment', 'Value': 'Production'}]
        instance_ids: List of specific instance IDs
        
    Returns:
        List of instance IDs
    """
    ec2 = boto3.client('ec2')
    instance_list = []
    
    if instance_ids:
        return instance_ids
    
    if tags:
        filters = [{'Name': f"tag:{tag['Key']}", 'Values': [tag['Value']]} for tag in tags]
        
        try:
            response = ec2.describe_instances(Filters=filters)
            for reservation in response['Reservations']:
                for instance in reservation['Instances']:
                    if instance['State']['Name'] == 'running':
                        instance_list.append(instance['InstanceId'])
            
            return instance_list
        except ClientError as e:
            print(f"Error fetching instances: {e}")
            return []
    
    # If no filters or instance IDs provided, get list from file
    try:
        with open("instance_ids.txt", "r") as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print("Error: instance_ids.txt file not found and no tags or instance IDs provided.")
        return []


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
        
        while not all_complete and retries < max_retries:
            time.sleep(10)
            retries += 1
            all_complete = True
            
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
        
        return {"success": True, "results": results}
    
    except ClientError as e:
        return {"success": False, "message": f"Error sending command: {str(e)}"}


def main():
    """Main function to update passwords across instances"""
    print("AWS SSM Password Update Tool")
    print("===========================")
    
    # Determine target instances
    print("\nHow would you like to select EC2 instances?")
    print("1. From a file (instance_ids.txt)")
    print("2. By tag (e.g., Environment=Production)")
    print("3. Specify instance IDs directly")
    
    choice = input("Enter your choice (1-3): ")
    
    instance_ids = []
    
    if choice == "1":
        try:
            with open("instance_ids.txt", "r") as f:
                instance_ids = [line.strip() for line in f if line.strip()]
            if not instance_ids:
                print("Error: No instance IDs found in instance_ids.txt")
                sys.exit(1)
        except FileNotFoundError:
            print("Error: instance_ids.txt file not found")
            print("Please create a file named 'instance_ids.txt' with one instance ID per line.")
            sys.exit(1)
    
    elif choice == "2":
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
        
        instance_ids = get_instance_ids(tags=tags)
    
    elif choice == "3":
        ids_input = input("Enter instance IDs separated by commas: ")
        instance_ids = [id.strip() for id in ids_input.split(",") if id.strip()]
    
    else:
        print("Invalid choice. Exiting.")
        sys.exit(1)
    
    if not instance_ids:
        print("No instances found or specified. Exiting.")
        sys.exit(1)
    
    print(f"\nFound {len(instance_ids)} instances:")
    for id in instance_ids:
        print(f"  - {id}")
    
    # Get target username and new password
    username = input("\nUsername to change password for: ")
    new_password = getpass.getpass("New password: ")
    confirm_password = getpass.getpass("Confirm new password: ")
    
    if new_password != confirm_password:
        print("Error: Passwords do not match")
        sys.exit(1)
    
    # Confirm before proceeding
    confirm = input(f"\nUpdate password for user '{username}' on {len(instance_ids)} instances? (y/n): ")
    if confirm.lower() != 'y':
        print("Operation cancelled.")
        sys.exit(0)
    
    # Execute password update
    print("\nUpdating passwords...")
    result = update_password(instance_ids, username, new_password)
    
    if not result["success"]:
        print(f"Error: {result['message']}")
        sys.exit(1)
    
    # Print results
    print("\nPassword Update Results:")
    print("=======================")
    
    success_count = sum(1 for instance_id, data in result["results"].items() 
                        if data["status"] == "Success")
    
    print(f"Successfully updated: {success_count}/{len(instance_ids)}")
    print(f"Failed: {len(instance_ids) - success_count}/{len(instance_ids)}")
    
    if len(instance_ids) - success_count > 0:
        print("\nInstances with errors:")
        for instance_id, data in result["results"].items():
            if data["status"] != "Success":
                print(f"  - {instance_id}: {data['status']} - {data['message']}")


if __name__ == "__main__":
    main()
