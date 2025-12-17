"""
Test SMDR sender - sends mock SMDR records to test the receiver.
"""
import socket
import time
import random
from datetime import datetime, timedelta


def generate_smdr_record(index):
    """Generate a realistic SMDR record."""
    # Random timestamp within the last hour
    now = datetime.now() - timedelta(seconds=random.randint(0, 3600))
    date_time = now.strftime("%Y/%m/%d %H:%M:%S")
    
    # Random call duration (00:00:03 to 00:05:00)
    duration_secs = random.randint(3, 300)
    duration = f"00:{duration_secs//60:02d}:{duration_secs%60:02d}"
    
    # Random extension
    extension = random.randint(200, 250)
    
    # Call direction (I=Inbound, O=Outbound)
    direction = random.choice(['I', 'O'])
    
    # Random phone numbers
    if direction == 'O':
        called = f"{random.randint(1000000000, 9999999999)}"
        dialed = f"9{called}"
    else:
        called = f"{random.randint(1000000000, 9999999999)}"
        dialed = called
    
    # Random call ID
    call_id = 1000000 + index
    
    # Random names
    names = ["John Smith", "Jane Doe", "David Rahn", "Alice Johnson", "Bob Williams"]
    name = random.choice(names)
    
    # Random trunk
    trunk = f"T{random.randint(9001, 9020)}"
    
    # Build SMDR line (simplified format based on observed data)
    record = f"{date_time},{duration},0,{extension},{direction},{called},{dialed},,0,{call_id},0,E{extension},{name},{trunk},Line{index % 10}"
    
    return record


def send_smdr_records(host='localhost', port=7004, count=10000, delay=0.01):
    """Send SMDR records to the receiver."""
    print(f"Connecting to {host}:{port}...")
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
        print(f"Connected! Sending {count} records...")
        
        start_time = time.time()
        
        for i in range(count):
            record = generate_smdr_record(i)
            sock.sendall((record + "\n").encode('utf-8'))
            
            # Show progress
            if (i + 1) % 100 == 0:
                elapsed = time.time() - start_time
                rate = (i + 1) / elapsed
                print(f"Sent {i + 1}/{count} records ({rate:.1f} records/sec)")
            
            # Small delay to avoid overwhelming the receiver
            if delay > 0:
                time.sleep(delay)
        
        elapsed = time.time() - start_time
        rate = count / elapsed
        print(f"\nCompleted! Sent {count} records in {elapsed:.2f} seconds ({rate:.1f} records/sec)")
        
        sock.close()
        
    except ConnectionRefusedError:
        print(f"Error: Could not connect to {host}:{port}. Is the SMDR receiver running?")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    import sys
    
    print("SMDR Test Sender")
    print("=" * 50)
    
    # Prompt for parameters
    host = input("Enter target host [localhost]: ").strip() or 'localhost'
    
    port_input = input("Enter target port [7004]: ").strip()
    port = int(port_input) if port_input else 7004
    
    count_input = input("Enter number of records to generate [10000]: ").strip()
    count = int(count_input) if count_input else 10000
    
    delay_input = input("Enter delay between records in seconds [0.01]: ").strip()
    delay = float(delay_input) if delay_input else 0.01
    
    print()
    print("Configuration:")
    print(f"  Target: {host}:{port}")
    print(f"  Records: {count}")
    print(f"  Delay: {delay}s between records")
    print("=" * 50)
    print()
    
    send_smdr_records(host, port, count, delay)
