import argparse
import os
import time
import opencue
import logging
from outline import Outline, cuerun
from outline.modules.shell import Shell

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def create_and_submit_job(scenario):
    logger.debug("Starting create_and_submit_job function")
    job_name = f"dummy_job_{scenario}_{int(time.time())}"
    logger.debug(f"Generated job name: {job_name}")

    try:
        logger.debug("Creating Outline object")
        ol = Outline(job_name, 
                     show=os.getenv('CUE_JOB_SHOW', 'testing'), 
                     shot=os.getenv('CUE_JOB_SHOT', 'default'), 
                     user=os.environ.get('USER', 'unknown'))
        
        logger.debug("Creating dummy layer")
        train_cmd = f"""/ParkCounty/apps/lnx-exo/cuedev/OpenCue/rqd/tests/test_dummy_processes.py"""
        dummy_layer = Shell("dummy_layer", command=train_cmd.split(), kill_signal="SIGTERM", threadable=True)
        ol.add_layer(dummy_layer)
        
        logger.debug("Launching job")
        result = cuerun.launch(ol, range="1-1", use_pycuerun=False)
        logger.debug(f"cuerun.launch returned: {result}")

        if isinstance(result, list):
            logger.debug("Result is a list, attempting to get first job")
            job = result[0] if result else None
        else:
            logger.debug("Result is not a list, assuming it's a single job")
            job = result
        
        if job:
            try:
                logger.info(f"Submitted job: {job.name()}")
                logger.debug(f"Job details - ID: {job.id()}, State: {job.state()}")
                return job
            except AttributeError as e:
                logger.error(f"Unexpected job object structure: {e}")
                logger.debug(f"Job object: {job}")
                return None
        else:
            logger.error("No job was created")
            return None

    except Exception as e:
        logger.error(f"Error in create_and_submit_job: {e}")
        logger.debug("Exception details", exc_info=True)
        return None

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
                    for _ in range(24):
                        time.sleep(5)
                        job = opencue.api.getJob(job.id())
                        state = job.state()
                        logger.info(f"Job State after kill request: {state}")
                        if state == opencue.api.job_pb2.FINISHED:
                            logger.info("Job completed successfully after kill request")
                            return job
                        elif state == opencue.api.job_pb2.DEAD:
                            logger.info("Job was successfully killed")
                            return job
                    
                    logger.warning("Job did not reach FINISHED or DEAD state after kill request")
                    logger.info("Attempting force kill")
                    job.kill(force=True)
                    
                    # Wait again after force kill to check if it's finished or dead
                    for _ in range(6):
                        time.sleep(5)
                        job = opencue.api.getJob(job.id())
                        state = job.state()
                        logger.info(f"Job State after force kill: {state}")
                        if state == opencue.api.job_pb2.FINISHED:
                            logger.info("Job completed successfully after force kill")
                            return job
                        elif state == opencue.api.job_pb2.DEAD:
                            logger.info("Job was successfully force killed")
                            return job
                    
                    logger.error("Job failed to reach terminal state even after force kill")
                        
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

def main():
    parser = argparse.ArgumentParser(description="OpenCue job submission and monitoring")
    parser.add_argument("--mode", choices=["submit"], required=True,
                        help="Mode: submit job")
    parser.add_argument("--scenario", choices=["success", "failure", "hang"], required=True,
                        help="Scenario to simulate: success, failure, or hang")
    parser.add_argument("--wait-time", type=int, default=5,
                        help="Time to wait before terminating the job (in seconds)")
    args = parser.parse_args()

    if args.mode == "submit":
        job = create_and_submit_job(args.scenario)
        if job:
            logger.info(f"Immediate job state: {job.state()}")
            job = monitor_job(job, args.wait_time)
            if job:
                final_state = job.state()
                logger.info(f"Final Job State: {final_state}")
                if final_state == opencue.api.job_pb2.FINISHED:
                    logger.info("Job completed successfully")
                elif final_state == opencue.api.job_pb2.DEAD:
                    logger.info("Job was terminated (killed or failed)")
                else:
                    logger.warning(f"Job ended in non-terminal state: {final_state}")
            else:
                logger.error("Failed to monitor job")
        else:
            logger.error("Failed to create and submit job")

if __name__ == "__main__":
    main()