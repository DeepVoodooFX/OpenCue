import argparse
import os
import time
import opencue
import logging
import threading
from outline import Outline, cuerun
from outline.modules.shell import Shell

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(threadName)s] %(levelname)s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def create_and_submit_job(scenario, wait_time, job_index, iteration):
    logger.info("Starting create_and_submit_job function")
    job_name = f"dummy_job_{scenario}_{iteration}_{int(time.time())}_{job_index}"
    logger.info(f"Generated job name: {job_name}")

    try:
        logger.info("Creating Outline object")
        ol = Outline(job_name,
                     show=os.getenv('CUE_JOB_SHOW', 'testing'),
                     shot=os.getenv('CUE_JOB_SHOT', 'default'),
                     user=os.environ.get('USER', 'unknown'))

        logger.info("Creating dummy layer")
        dummy_command = f"""python3 /ParkCounty/apps/lnx-exo/cuedev/Opencue/rqd/tests/dummy_processes.py --scenario {scenario} --wait-time {wait_time}"""
        dummy_layer = Shell("dummy_layer", range='1-10', command=dummy_command.split(), kill_signal="SIGTERM", threadable=True)
        ol.add_layer(dummy_layer)

        logger.info("Launching job")
        result = cuerun.launch(ol, range="1-10", use_pycuerun=False)
        logger.info(f"cuerun.launch returned: {result}")

        if isinstance(result, list):
            logger.info("Result is a list, attempting to get first job")
            job = result[0] if result else None
        else:
            logger.info("Result is not a list, assuming it's a single job")
            job = result

        if job:
            try:
                logger.info(f"Submitted job: {job.name()}")
                logger.info(f"Job details - ID: {job.id()}, State: {job.state()}")
                return job
            except AttributeError as e:
                logger.error(f"Unexpected job object structure: {e}")
                logger.info(f"Job object: {job}")
                return None
        else:
            logger.error("No job was created")
            return None

    except Exception as e:
        logger.error(f"Error in create_and_submit_job: {e}")
        logger.info("Exception details", exc_info=True)
        return None

def monitor_frame_states(job):
    frames = job.getFrames()
    for frame in frames:
        state_code = frame.state()
        state_name = get_frame_state_name(state_code)
        logger.info(f"Frame {frame.number()} state: {state_name} (State code: {state_code})")
        logger.debug(f"Frame details - ID: {frame.id()}, Layer: {frame.layer()}")

def get_frame_state_name(state_code):
    state_names = {
        opencue.api.job_pb2.WAITING: 'WAITING',
        opencue.api.job_pb2.SETUP: 'SETUP',
        opencue.api.job_pb2.RUNNING: 'RUNNING',
        opencue.api.job_pb2.SUCCEEDED: 'SUCCEEDED',
        opencue.api.job_pb2.DEPEND: 'DEPEND',
        opencue.api.job_pb2.DEAD: 'DEAD',
        opencue.api.job_pb2.EATEN: 'EATEN',
        opencue.api.job_pb2.CHECKPOINT: 'CHECKPOINT',
        opencue.api.job_pb2.TERMINATING: 'TERMINATING'
    }
    return state_names.get(state_code, f"UNKNOWN({state_code})")

def monitor_job(job, wait_time):
    logger.info(f"Starting to monitor job: {job.name()}")
    logger.info(f"Job ID: {job.id()}")

    start_time = time.time()
    kill_attempts = 0
    max_kill_attempts = 3

    while True:
        try:
            job = opencue.api.getJob(job.id())
            state = job.state()
            state_name = get_job_state_name(state)
            logger.info(f"Job {job.name()} State: {state_name} (State code: {state})")
            monitor_frame_states(job)

            if state == opencue.api.job_pb2.FINISHED:
                logger.info(f"Job {job.name()} completed successfully")
                break
            elif state == opencue.api.job_pb2.DEAD:
                logger.info(f"Job {job.name()} failed or was killed")
                break

            elapsed_time = time.time() - start_time
            if elapsed_time > wait_time or kill_attempts > 0:
                if kill_attempts == 0:
                    logger.info(f"Job {job.name()} has exceeded its runtime. Initiating shutdown.")
                try:
                    job.kill()
                    kill_attempts += 1
                    logger.info(f"Kill request sent to job {job.name()} (Attempt {kill_attempts})")
                    # Wait for the job to be killed
                    for _ in range(60):  # Wait for up to 1 minute
                        time.sleep(3)
                        job = opencue.api.getJob(job.id())
                        state = job.state()
                        frames = job.getFrames()
                        running_frames = False
                        for frame in frames:
                            state_code = frame.state()
                            state_name = get_frame_state_name(state_code)
                            logger.info(f"Frame state after kill request: {state_name}")
                            if state_code in [opencue.api.job_pb2.RUNNING, opencue.api.job_pb2.WAITING, opencue.api.job_pb2.TERMINATING]:
                                running_frames = True
                                break  # Exit the inner loop
                        if not running_frames:
                            break  # Exit the waiting loop if no frames are running

                        logger.info(f"Job State after kill request: {state_name}")

                        if state == opencue.api.job_pb2.FINISHED:
                            logger.info(f"Job {job.name()} completed successfully after kill request")
                            break
                        elif state == opencue.api.job_pb2.DEAD:
                            logger.info(f"Job {job.name()} was successfully killed")
                            break

                    if running_frames and kill_attempts < max_kill_attempts:
                        logger.warning(f"Job {job.name()} still has running frames after kill attempt. Will retry.")
                        continue  # Go to the next iteration of the main loop to try killing again
                    elif kill_attempts >= max_kill_attempts:
                        logger.error(f"Failed to kill job {job.name()} after {max_kill_attempts} attempts. Exiting monitor.")
                        break
                except Exception as e:
                    logger.error(f"Failed to kill job {job.name()}: {e}")
                    break
            time.sleep(5)  # Wait for 5 seconds before checking again
        except opencue.exception.EntityNotFoundException:
            logger.warning(f"Job {job.name()} not found. Exiting monitor.")
            break
        except Exception as e:
            logger.error(f"Error monitoring job {job.name()}: {e}")
            logger.debug("Exception details", exc_info=True)
            break

    final_state_code = job.state()
    final_state_name = get_job_state_name(final_state_code)
    logger.info(f"Final Job State for {job.name()}: {final_state_name} (State code: {final_state_code})")
    log_detailed_job_info(job)

def get_job_state_name(state_code):
    state_names = {
        opencue.api.job_pb2.PENDING: 'PENDING',
        opencue.api.job_pb2.FINISHED: 'FINISHED',
        opencue.api.job_pb2.RUNNING: 'RUNNING',
        opencue.api.job_pb2.DEAD: 'DEAD',
        opencue.api.job_pb2.SUCCEEDED: 'SUCCEEDED',
    }
    return state_names.get(state_code, f"UNKNOWN({state_code})")

def log_detailed_job_info(job):
    logger.info("Detailed Job Information:")
    logger.info(f"  Name: {job.name()}")
    logger.info(f"  ID: {job.id()}")
    logger.info(f"  State: {get_job_state_name(job.state())}")
    logger.info(f"  Start Time: {job.startTime()}")
    logger.info(f"  Stop Time: {job.stopTime()}")

    frames = job.getFrames()
    for frame in frames:
        logger.info(f"  Frame {frame.number()}:")
        logger.info(f"    State: {get_frame_state_name(frame.state())}")
        logger.info(f"    Exit Status: {frame.exitStatus()}")
        logger.info(f"    Start Time: {frame.startTime()}")
        logger.info(f"    Stop Time: {frame.stopTime()}")
        logger.info(f"    Run Time: {frame.runTime()}")

def main():
    parser = argparse.ArgumentParser(description="OpenCue job submission and monitoring")
    parser.add_argument("--scenario", choices=["success", "failure", "hang"], required=True,
                        help="Scenario to simulate: success, failure, or hang")
    parser.add_argument("--wait-time", type=int, default=5,
                        help="Time to wait before terminating the job (in seconds)")
    args = parser.parse_args()

    total_iterations = 50
    for iteration in range(1, total_iterations + 1):
        logger.info(f"=== Starting iteration {iteration} of {total_iterations} ===")
        jobs = []
        for i in range(2):  # Submitting 2 jobs each iteration
            job = create_and_submit_job(args.scenario, args.wait_time, i, iteration)
            if job:
                jobs.append(job)
            else:
                logger.error(f"Failed to create and submit job {i} in iteration {iteration}")

        if jobs:
            threads = []
            for job in jobs:
                t = threading.Thread(target=monitor_job, args=(job, args.wait_time))
                t.start()
                threads.append(t)

            # Wait for all threads to complete
            for t in threads:
                t.join()

            logger.info(f"Iteration {iteration} completed. All jobs have been monitored.")
        else:
            logger.error(f"No jobs were created successfully in iteration {iteration}")

        logger.info(f"=== Completed iteration {iteration} of {total_iterations} ===\n")

    logger.info("All iterations completed.")

if __name__ == "__main__":
    main()