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
    logger.info(f"Received SIGTERM. Signal number: {signum}")
    logger.info(f"Current time: {time.time()}")
    logger.info(f"Process ID: {os.getpid()}")
    logger.info(f"Parent Process ID: {os.getppid()}")
    logger.info("Preparing to exit.")
    # Set frame state to terminating
    global should_exit
    should_exit = True

def run_dummy_process(scenario, wait_time):
    global should_exit
    should_exit = False
    signal.signal(signal.SIGTERM, sigterm_handler)
    
    logger.info(f"Running dummy process with scenario: {scenario}")
    logger.info(f"Process ID: {os.getpid()}")
    logger.info(f"Parent Process ID: {os.getppid()}")
    start_time = time.time()
    
    while True:
        current_time = time.time()
        if should_exit or (current_time - start_time >= wait_time):
            if scenario == "success":
                logger.info("Exiting successfully")
                sys.exit(0)
            elif scenario == "failure":
                logger.info("Exiting with failure")
                sys.exit(1)
            elif scenario == "hang":
                logger.info("Hanging indefinitely")
                hang_start = time.time()
                while True:
                    if should_exit:
                        logger.info(f"Exiting hang scenario after {time.time() - hang_start} seconds")
                        sys.exit(0)
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