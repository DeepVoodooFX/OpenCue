-- Add kill_signal column to layer table
ALTER TABLE layer 
ADD COLUMN str_kill_signal VARCHAR(10) DEFAULT 'SIGKILL';

-- Add constraint for kill_signal
ALTER TABLE layer ADD CONSTRAINT chk_layer_kill_signal 
    CHECK (str_kill_signal IN ('SIGTERM', 'SIGKILL', 'SIGINT', 'SIGHUP', 'SIGUSR1', 'SIGUSR2'));

-- Update existing rows
UPDATE layer SET str_kill_signal = 'SIGKILL' WHERE str_kill_signal IS NULL;