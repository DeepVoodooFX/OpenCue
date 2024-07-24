import argparse
import os
import time
import opencue
import logging
from outline import Outline, cuerun
from outline.modules.shell import Shell

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def create_and_submit_job(scenario, wait_time):
    logger.info("Starting create_and_submit_job function")
    job_name = f"dummy_job_{scenario}_{int(time.time())}"
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
        result = cuerun.launch(ol, range="1-5", use_pycuerun=False)
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
        0: opencue.api.job_pb2.WAITING,
        1: opencue.api.job_pb2.SETUP,
        2: opencue.api.job_pb2.RUNNING,
        3: opencue.api.job_pb2.SUCCEEDED,
        4: opencue.api.job_pb2.DEPEND,
        5: opencue.api.job_pb2.DEAD,
        6: opencue.api.job_pb2.EATEN,
        7: opencue.api.job_pb2.CHECKPOINT,
        8: opencue.api.job_pb2.TERMINATING
    }
    return state_names.get(state_code, f"UNKNOWN({state_code})")

def monitor_job(job, wait_time):
    if not job:
        logger.error("No job provided to monitor_job function")
        return None

    logger.info(f"Starting to monitor job: {job.name()}")
    logger.info(f"Job ID: {job.id()}")
    
    start_time = time.time()

    while True:
        try:
            job = opencue.api.getJob(job.id())
            state = job.state()
            logger.info(f"Job State: {state}")
            monitor_frame_states(job)
            
            if state == opencue.api.job_pb2.FINISHED:
                logger.info("Job completed successfully")
                return job
            elif state == opencue.api.job_pb2.DEAD:
                logger.info("Job failed or was killed")
                return job
            
            elapsed_time = time.time() - start_time
            if elapsed_time > wait_time:
                logger.info(f"Job {job.name()} has exceeded its runtime. Initiating shutdown.")
                try:
                    job.kill()
                    logger.info(f"Kill request sent to job {job.name()}")
                    
                    # Wait for the job to be killed
                    for _ in range(1024):
                        time.sleep(0.01)
                        job = opencue.api.getJob(job.id())
                        state = job.state()
                        frames = job.getFrames()
                        running_frames = False
                        for frame in frames:
                            state_code = frame.state()
                            state_name = get_frame_state_name(state_code)
                            logger.info(f"Frame state after kill request: {state_name}")
                            if state_name in [opencue.api.job_pb2.RUNNING, opencue.api.job_pb2.WAITING, opencue.api.job_pb2.TERMINATING]:
                                running_frames = True
                                break  # Exit the inner loop
                        
                        if running_frames:
                            continue  # Go to the next iteration of the outer loop

                        logger.info(f"Job State after kill request: {state}")

                        if state == opencue.api.job_pb2.FINISHED:
                            logger.info("Job completed successfully after kill request")
                            return job
                        elif state == opencue.api.job_pb2.DEAD:
                            logger.info("Job was successfully killed")
                            return job
                except Exception as e:
                    logger.error(f"Failed to kill job {job.name()}: {e}")
                break
            
            time.sleep(5)  # Wait for 5 seconds before checking again
            
        except opencue.exception.EntityNotFoundException:
            logger.warning(f"Job not found. Exiting monitor.")
            break
        except Exception as e:
            logger.error(f"Error monitoring job: {e}")
            logger.debug("Exception details", exc_info=True)
            break

    logger.warning(f"Job monitoring ended without reaching a terminal state. Final state: {state}")
    return job

def get_job_state_name(state_code):
    state_names = {
        0: opencue.api.job_pb2.PENDING,
        1: opencue.api.job_pb2.FINISHED,
        2: opencue.api.job_pb2.STARTUP,
        3: opencue.api.job_pb2.SHUTDOWN,
        4: opencue.api.job_pb2.POSTED,
    }
    return state_names.get(state_code, f"UNKNOWN({state_code})")

def submit_and_monitor(scenario, wait_time):
    job = create_and_submit_job(scenario, wait_time)
    if job:
        initial_state_code = job.state()
        initial_state_name = get_job_state_name(initial_state_code)
        logger.info(f"Immediate job state: {initial_state_name} (State code: {initial_state_code})")
        
        job = monitor_job(job, wait_time)

        if job:
            final_state_code = job.state()
            final_state_name = get_job_state_name(final_state_code)
            logger.info(f"Final Job State: {final_state_name} (State code: {final_state_code})")
            
            # Log detailed job information
            log_detailed_job_info(job)
            
            if final_state_code == opencue.api.job_pb2.FINISHED:
                logger.info("Job completed successfully")
            elif final_state_code == opencue.api.job_pb2.DEAD:
                logger.info("Job was terminated (killed or failed)")
            else:
                logger.warning(f"Job ended in non-terminal state: {final_state_name}")
        else:
            logger.error("Failed to monitor job")
    else:
        logger.error("Failed to create and submit job")

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

    submit_and_monitor(args.scenario, args.wait_time)

if __name__ == "__main__":
    main()