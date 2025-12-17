"""
Service management utility for SMDR Receiver service.
Provides easy commands to install, start, stop, and remove the Windows service.
"""
import sys
import os
import subprocess

SERVICE_NAME = "SMDRReceiver"


def run_command(cmd):
    """Run a command and return the result."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
        print(result.stdout)
        if result.stderr:
            print(result.stderr)
        return result.returncode == 0
    except Exception as e:
        print(f"Error: {e}")
        return False


def install_service():
    """Install the SMDR service."""
    print("Installing SMDR Receiver service...")
    cmd = f'python smdr_service.py install'
    if run_command(cmd):
        print("Service installed successfully.")
        print(f"Service Name: {SERVICE_NAME}")
        return True
    return False


def remove_service():
    """Remove the SMDR service."""
    print("Removing SMDR Receiver service...")
    cmd = f'python smdr_service.py remove'
    if run_command(cmd):
        print("Service removed successfully.")
        return True
    return False


def start_service():
    """Start the SMDR service."""
    print("Starting SMDR Receiver service...")
    cmd = f'python smdr_service.py start'
    if run_command(cmd):
        print("Service started successfully.")
        return True
    return False


def stop_service():
    """Stop the SMDR service."""
    print("Stopping SMDR Receiver service...")
    cmd = f'python smdr_service.py stop'
    if run_command(cmd):
        print("Service stopped successfully.")
        return True
    return False


def restart_service():
    """Restart the SMDR service."""
    print("Restarting SMDR Receiver service...")
    stop_service()
    return start_service()


def status_service():
    """Check the status of the SMDR service."""
    print(f"Checking status of {SERVICE_NAME}...")
    cmd = f'sc query {SERVICE_NAME}'
    run_command(cmd)


def show_menu():
    """Show the management menu."""
    print("\n" + "=" * 50)
    print("SMDR Receiver Service Management")
    print("=" * 50)
    print("1. Install service")
    print("2. Start service")
    print("3. Stop service")
    print("4. Restart service")
    print("5. Remove service")
    print("6. Check status")
    print("7. Exit")
    print("=" * 50)
    

def main():
    """Main menu loop."""
    # Check if running as administrator
    try:
        import ctypes
        is_admin = ctypes.windll.shell32.IsUserAnAdmin()
        if not is_admin:
            print("\nWARNING: This script should be run as Administrator!")
            print("Right-click and select 'Run as administrator'\n")
    except:
        pass
    
    while True:
        show_menu()
        choice = input("\nEnter your choice (1-7): ").strip()
        
        if choice == '1':
            install_service()
        elif choice == '2':
            start_service()
        elif choice == '3':
            stop_service()
        elif choice == '4':
            restart_service()
        elif choice == '5':
            stop_service()
            remove_service()
        elif choice == '6':
            status_service()
        elif choice == '7':
            print("Exiting...")
            break
        else:
            print("Invalid choice. Please try again.")
        
        input("\nPress Enter to continue...")


if __name__ == "__main__":
    main()
