import argparse
import time
import signal
import sys
import logging
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s - PID:%(process)d - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
should_exit = False

def sigterm_handler(signum, frame):
    print(f"Received SIGTERM. Signum: {signum}, Frame: {frame}")
    print(f"Current time: {time.time()}")
    print(f"Process ID: {os.getpid()}")
    print(f"Parent Process ID: {os.getppid()}")
    print("Preparing to exit.")
    # Set frame state to terminating
    global should_exit
    should_exit = True

def run_dummy_process(scenario, wait_time):
    print("Starting run_dummy_process")
    global should_exit
    should_exit = False
    print("Setting up SIGTERM handler")
    signal.signal(signal.SIGTERM, sigterm_handler)
    signal.signal(signal.SIGINT, sigterm_handler)
    print("SIGTERM handler set up complete")
    
    print(f"Running dummy process with scenario: {scenario}")
    print(f"Process ID: {os.getpid()}")
    print(f"Parent Process ID: {os.getppid()}")
    start_time = time.time()

    end_time = time.time() + wait_time
    while time.time() < end_time and not should_exit:
        signal.pause()
    
    while True:
        current_time = time.time()
        if should_exit or (current_time - start_time >= wait_time):
            if scenario == "success":
                print("Exiting successfully")
                sys.exit(0)
            elif scenario == "failure":
                print("Exiting with failure")
                sys.exit(1)
            elif scenario == "hang":
                print("Hanging indefinitely")
                hang_start = time.time()
                while True:
                    print(f"Hanging since {hang_start}")
                    time.sleep(1)
        time.sleep(0.1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dummy process for OpenCue testing")
    parser.add_argument("--scenario", choices=["success", "failure", "hang"], required=True,
                        help="Scenario to simulate: success, failure, or hang")
    parser.add_argument("--wait-time", type=int, default=5,
                        help="Time to wait before terminating the process (in seconds)")
    args = parser.parse_args()

    run_dummy_process(args.scenario, args.wait_time)