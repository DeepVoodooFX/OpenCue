ALTER TABLE layer 
ADD COLUMN str_kill_signal VARCHAR(10) DEFAULT 'SIGKILL';

-- Add int_terminating_count to relevant tables
ALTER TABLE job_stat ADD COLUMN int_terminating_count BIGINT DEFAULT 0 NOT NULL;
ALTER TABLE layer_stat ADD COLUMN int_terminating_count BIGINT DEFAULT 0 NOT NULL;
ALTER TABLE job_history ADD COLUMN int_terminating_count BIGINT DEFAULT 0 NOT NULL;
ALTER TABLE layer_history ADD COLUMN int_terminating_count BIGINT DEFAULT 0 NOT NULL;

-- Add indexes for improved query performance
CREATE INDEX idx_job_stat_terminating ON job_stat (int_terminating_count);
CREATE INDEX idx_layer_stat_terminating ON layer_stat (int_terminating_count);
CREATE INDEX idx_job_history_terminating ON job_history (int_terminating_count);
CREATE INDEX idx_layer_history_terminating ON layer_history (int_terminating_count);
CREATE INDEX idx_frame_terminating ON frame (pk_job, pk_layer) WHERE str_state = 'TERMINATING';

-- Alter existing types to add int_terminating_count
ALTER TYPE JobStatType ADD ATTRIBUTE int_terminating_count BIGINT;
ALTER TYPE LayerStatType ADD ATTRIBUTE int_terminating_count BIGINT;

-- Update views (same as before)
DROP VIEW v_history_job;
CREATE VIEW v_history_job (pk_job, str_name, str_shot, str_user, int_core_time_success, int_core_time_fail, int_gpu_time_success, int_gpu_time_fail, int_frame_count, int_layer_count, int_waiting_count, int_dead_count, int_depend_count, int_eaten_count, int_terminating_count, int_succeeded_count, int_running_count, int_max_rss, int_gpu_mem_max, b_archived, str_facility_name, str_dept_name, int_ts_started, int_ts_stopped, str_show_name, dt_last_modified) AS
  select
jh.PK_JOB,
jh.STR_NAME,
jh.STR_SHOT,
jh.STR_USER,
jh.INT_CORE_TIME_SUCCESS,
jh.INT_CORE_TIME_FAIL,
jh.INT_GPU_TIME_SUCCESS,
jh.INT_GPU_TIME_FAIL,
jh.INT_FRAME_COUNT,
jh.INT_LAYER_COUNT,
jh.INT_WAITING_COUNT,
jh.INT_DEAD_COUNT,
jh.INT_DEPEND_COUNT,
jh.INT_EATEN_COUNT,
jh.INT_TERMINATING_COUNT,
jh.INT_SUCCEEDED_COUNT,
jh.INT_RUNNING_COUNT,
jh.INT_MAX_RSS,
jh.INT_GPU_MEM_MAX,
jh.B_ARCHIVED,
f.str_name STR_FACILITY_NAME,
d.str_name str_dept_name,
jh.INT_TS_STARTED,
jh.INT_TS_STOPPED,
s.str_name str_show_name,
jh.dt_last_modified
from job_history jh, show s, facility f, dept d
where jh.pk_show   = s.pk_show
and jh.pk_facility = f.pk_facility
and jh.pk_dept     = d.pk_dept
and (
    jh.dt_last_modified >= (
        select dt_begin
        from history_period
    )
    or
    jh.int_ts_stopped = 0
);


DROP VIEW v_history_layer;
CREATE VIEW v_history_layer (pk_layer, pk_job, str_name, str_type, int_cores_min,
    int_mem_min, int_gpus_min, int_gpu_mem_min, int_core_time_success, int_core_time_fail,
    int_gpu_time_success, int_gpu_time_fail, int_frame_count, int_layer_count,
    int_waiting_count, int_dead_count, int_depend_count, int_eaten_count, int_terminating_count, int_succeeded_count,
    int_running_count, int_max_rss, int_gpu_mem_max, b_archived, str_services, str_show_name, dt_last_modified) AS
  SELECT
lh.PK_LAYER,
lh.PK_JOB,
lh.STR_NAME,
lh.STR_TYPE,
lh.INT_CORES_MIN,
lh.INT_MEM_MIN,
lh.INT_GPUS_MIN,
lh.INT_GPU_MEM_MIN,
lh.INT_CORE_TIME_SUCCESS,
lh.INT_CORE_TIME_FAIL,
lh.INT_GPU_TIME_SUCCESS,
lh.INT_GPU_TIME_FAIL,
lh.INT_FRAME_COUNT,
lh.INT_LAYER_COUNT,
lh.INT_WAITING_COUNT,
lh.INT_DEAD_COUNT,
lh.INT_DEPEND_COUNT,
lh.INT_EATEN_COUNT,
lh.INT_TERMINATING_COUNT,
lh.INT_SUCCEEDED_COUNT,
lh.INT_RUNNING_COUNT,
lh.INT_MAX_RSS,
lh.INT_GPU_MEM_MAX,
lh.B_ARCHIVED,
lh.STR_SERVICES,
s.str_name str_show_name,
lh.dt_last_modified
from layer_history lh, job_history jh, show s
where lh.pk_job = jh.pk_job
and jh.pk_show  = s.pk_show
and jh.dt_last_modified >= (
    select dt_begin
    from history_period
)
and jh.dt_last_modified < (
    select dt_end
    from history_period
);

-- Add a new trigger to handle transition to and from TERMINATING state
CREATE OR REPLACE FUNCTION trigger__handle_terminating_state()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.str_state = 'TERMINATING' AND OLD.str_state != 'TERMINATING' THEN
        -- Frame is entering TERMINATING state
        UPDATE job_stat SET int_terminating_count = int_terminating_count + 1 WHERE pk_job = NEW.pk_job;
        UPDATE layer_stat SET int_terminating_count = int_terminating_count + 1 WHERE pk_layer = NEW.pk_layer;
    ELSIF OLD.str_state = 'TERMINATING' AND NEW.str_state != 'TERMINATING' THEN
        -- Frame is leaving TERMINATING state
        UPDATE job_stat SET int_terminating_count = int_terminating_count - 1 WHERE pk_job = NEW.pk_job;
        UPDATE layer_stat SET int_terminating_count = int_terminating_count - 1 WHERE pk_layer = NEW.pk_layer;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER handle_terminating_state
BEFORE UPDATE ON frame
FOR EACH ROW
WHEN (OLD.str_state IS DISTINCT FROM NEW.str_state)
EXECUTE FUNCTION trigger__handle_terminating_state();


CREATE FUNCTION trigger__update_frame_to_terminating()
RETURNS TRIGGER AS $body$
BEGIN
    NEW.str_state := 'TERMINATING';
    NEW.ts_updated := current_timestamp;
    NEW.int_version := NEW.int_version + 1;
    RETURN NEW;
END;
$body$
LANGUAGE PLPGSQL;

CREATE TRIGGER update_frame_to_terminating BEFORE UPDATE ON frame
FOR EACH ROW
  WHEN (NEW.str_state = 'TERMINATING' AND OLD.str_state = 'RUNNING')
  EXECUTE PROCEDURE trigger__update_frame_to_terminating();

CREATE FUNCTION trigger__check_terminating_timeout()
RETURNS TRIGGER AS $body$
BEGIN
    IF NEW.str_state = 'TERMINATING' AND 
       (EXTRACT(EPOCH FROM (current_timestamp - NEW.ts_updated)) > 60) THEN
        NEW.str_state := 'DEAD';
        NEW.int_exit_status := 1;
    END IF;
    RETURN NEW;
END;
$body$
LANGUAGE PLPGSQL;

CREATE TRIGGER check_terminating_timeout BEFORE UPDATE ON frame
FOR EACH ROW
  WHEN (NEW.str_state = 'TERMINATING')
  EXECUTE PROCEDURE trigger__check_terminating_timeout();

CREATE OR REPLACE FUNCTION trigger__before_delete_job()
RETURNS TRIGGER AS $body$
DECLARE
    js JobStatType;
BEGIN
    IF NOT EXISTS (SELECT FROM config WHERE str_key='DISABLE_HISTORY') THEN

        SELECT
            job_usage.int_core_time_success,
            job_usage.int_core_time_fail,
            job_usage.int_gpu_time_success,
            job_usage.int_gpu_time_fail,
            job_stat.int_waiting_count,
            job_stat.int_dead_count,
            job_stat.int_depend_count,
            job_stat.int_eaten_count,
            job_stat.int_terminating_count,
            job_stat.int_succeeded_count,
            job_stat.int_running_count,
            job_mem.int_max_rss,
            job_mem.int_gpu_mem_max
        INTO
            js
        FROM
            job_mem,
            job_usage,
            job_stat
        WHERE
            job_usage.pk_job = job_mem.pk_job
        AND
            job_stat.pk_job = job_mem.pk_job
        AND
            job_mem.pk_job = OLD.pk_job;

        UPDATE
            job_history
        SET
            pk_dept = OLD.pk_dept,
            int_core_time_success = js.int_core_time_success,
            int_core_time_fail = js.int_core_time_fail,
            int_gpu_time_success = js.int_gpu_time_success,
            int_gpu_time_fail = js.int_gpu_time_fail,
            int_frame_count = OLD.int_frame_count,
            int_layer_count = OLD.int_layer_count,
            int_waiting_count = js.int_waiting_count,
            int_dead_count = js.int_dead_count,
            int_depend_count = js.int_depend_count,
            int_eaten_count = js.int_eaten_count,
            int_terminating_count = js.int_terminating_count,
            int_succeeded_count = js.int_succeeded_count,
            int_running_count = js.int_running_count,
            int_max_rss = js.int_max_rss,
            int_gpu_mem_max = js.int_gpu_mem_max,
            b_archived = true,
            int_ts_stopped = COALESCE(epoch(OLD.ts_stopped), epoch(current_timestamp))
        WHERE
            pk_job = OLD.pk_job;

    END IF;

    DELETE FROM depend WHERE pk_job_depend_on=OLD.pk_job OR pk_job_depend_er=OLD.pk_job;
    DELETE FROM frame WHERE pk_job=OLD.pk_job;
    DELETE FROM layer WHERE pk_job=OLD.pk_job;
    DELETE FROM job_env WHERE pk_job=OLD.pk_job;
    DELETE FROM job_stat WHERE pk_job=OLD.pk_job;
    DELETE FROM job_resource WHERE pk_job=OLD.pk_job;
    DELETE FROM job_usage WHERE pk_job=OLD.pk_job;
    DELETE FROM job_mem WHERE pk_job=OLD.pk_job;
    DELETE FROM comments WHERE pk_job=OLD.pk_job;

    RETURN OLD;
END
$body$
LANGUAGE PLPGSQL;

CREATE OR REPLACE FUNCTION trigger__after_job_finished()
RETURNS TRIGGER AS $body$
DECLARE
    ts INT := cast(epoch(current_timestamp) as integer);
    js JobStatType;
    ls LayerStatType;
    one_layer RECORD;
BEGIN
    IF NOT EXISTS (SELECT FROM config WHERE str_key='DISABLE_HISTORY') THEN

        SELECT
            job_usage.int_core_time_success,
            job_usage.int_core_time_fail,
            job_usage.int_gpu_time_success,
            job_usage.int_gpu_time_fail,
            job_stat.int_waiting_count,
            job_stat.int_dead_count,
            job_stat.int_depend_count,
            job_stat.int_eaten_count,
            job_stat.int_terminating_count,
            job_stat.int_succeeded_count,
            job_stat.int_running_count,
            job_mem.int_max_rss,
            job_mem.int_gpu_mem_max
        INTO
            js
        FROM
            job_mem,
            job_usage,
            job_stat
        WHERE
            job_usage.pk_job = job_mem.pk_job
        AND
            job_stat.pk_job = job_mem.pk_job
        AND
            job_mem.pk_job = NEW.pk_job;

        UPDATE
            job_history
        SET
            pk_dept = NEW.pk_dept,
            int_core_time_success = js.int_core_time_success,
            int_core_time_fail = js.int_core_time_fail,
            int_gpu_time_success = js.int_gpu_time_success,
            int_gpu_time_fail = js.int_gpu_time_fail,
            int_frame_count = NEW.int_frame_count,
            int_layer_count = NEW.int_layer_count,
            int_waiting_count = js.int_waiting_count,
            int_dead_count = js.int_dead_count,
            int_depend_count = js.int_depend_count,
            int_eaten_count = js.int_eaten_count,
            int_terminating_count = js.int_terminating_count,
            int_succeeded_count = js.int_succeeded_count,
            int_running_count = js.int_running_count,
            int_max_rss = js.int_max_rss,
            int_gpu_mem_max = js.int_gpu_mem_max,
            int_ts_stopped = ts
        WHERE
            pk_job = NEW.pk_job;

        FOR one_layer IN (SELECT pk_layer from layer where pk_job = NEW.pk_job)
        LOOP
            SELECT
                layer_usage.int_core_time_success,
                layer_usage.int_core_time_fail,
                layer_usage.int_gpu_time_success,
                layer_usage.int_gpu_time_fail,
                layer_stat.int_total_count,
                layer_stat.int_waiting_count,
                layer_stat.int_dead_count,
                layer_stat.int_depend_count,
                layer_stat.int_eaten_count,
                layer_stat.int_terminating_count,
                layer_stat.int_succeeded_count,
                layer_stat.int_running_count,
                layer_mem.int_max_rss,
                layer_mem.int_gpu_mem_max
            INTO
                ls
            FROM
                layer_mem,
                layer_usage,
                layer_stat
            WHERE
                layer_usage.pk_layer = layer_mem.pk_layer
            AND
                layer_stat.pk_layer = layer_mem.pk_layer
            AND
                layer_mem.pk_layer = one_layer.pk_layer;

            UPDATE
                layer_history
            SET
                int_core_time_success = ls.int_core_time_success,
                int_core_time_fail = ls.int_core_time_fail,
                int_gpu_time_success = ls.int_gpu_time_success,
                int_gpu_time_fail = ls.int_gpu_time_fail,
                int_frame_count = ls.int_total_count,
                int_waiting_count = ls.int_waiting_count,
                int_dead_count = ls.int_dead_count,
                int_depend_count = ls.int_depend_count,
                int_eaten_count = ls.int_eaten_count,
                int_terminating_count = ls.int_terminating_count,
                int_succeeded_count = ls.int_succeeded_count,
                int_running_count = ls.int_running_count,
                int_max_rss = ls.int_max_rss,
                int_gpu_mem_max = ls.int_gpu_mem_max
            WHERE
                pk_layer = one_layer.pk_layer;
        END LOOP;

    END IF;

    /**
     * Delete any local core assignments from this job.
     **/
    DELETE FROM job_local WHERE pk_job=NEW.pk_job;

    RETURN NEW;
END;
$body$
LANGUAGE PLPGSQL;

CREATE OR REPLACE FUNCTION trigger__before_delete_layer()
RETURNS TRIGGER AS $body$
DECLARE
    js LayerStatType;
BEGIN
    IF NOT EXISTS (SELECT FROM config WHERE str_key='DISABLE_HISTORY') THEN

        SELECT
            layer_usage.int_core_time_success,
            layer_usage.int_core_time_fail,
            layer_usage.int_gpu_time_success,
            layer_usage.int_gpu_time_fail,
            layer_stat.int_total_count,
            layer_stat.int_waiting_count,
            layer_stat.int_dead_count,
            layer_stat.int_depend_count,
            layer_stat.int_eaten_count,
            layer_stat.int_terminating_count,
            layer_stat.int_succeeded_count,
            layer_stat.int_running_count,
            layer_mem.int_max_rss,
            layer_mem.int_gpu_mem_max
        INTO
            js
        FROM
            layer_mem,
            layer_usage,
            layer_stat
        WHERE
            layer_usage.pk_layer = layer_mem.pk_layer
        AND
            layer_stat.pk_layer = layer_mem.pk_layer
        AND
            layer_mem.pk_layer = OLD.pk_layer;

        UPDATE
            layer_history
        SET
            int_core_time_success = js.int_core_time_success,
            int_core_time_fail = js.int_core_time_fail,
            int_gpu_time_success = js.int_gpu_time_success,
            int_gpu_time_fail = js.int_gpu_time_fail,
            int_frame_count = js.int_total_count,
            int_waiting_count = js.int_waiting_count,
            int_dead_count = js.int_dead_count,
            int_depend_count = js.int_depend_count,
            int_eaten_count = js.int_eaten_count,
            int_terminating_count = js.int_terminating_count,
            int_succeeded_count = js.int_succeeded_count,
            int_running_count = js.int_running_count,
            int_max_rss = js.int_max_rss,
            int_gpu_mem_max = js.int_gpu_mem_max,
            b_archived = true
        WHERE
            pk_layer = OLD.pk_layer;

    END IF;

    DELETE FROM layer_resource where pk_layer=OLD.pk_layer;
    DELETE FROM layer_stat where pk_layer=OLD.pk_layer;
    DELETE FROM layer_usage where pk_layer=OLD.pk_layer;
    DELETE FROM layer_env where pk_layer=OLD.pk_layer;
    DELETE FROM layer_mem where pk_layer=OLD.pk_layer;
    DELETE FROM layer_output where pk_layer=OLD.pk_layer;

    RETURN OLD;
END;
$body$
LANGUAGE PLPGSQL;