# keepalive

A quick utility to help you increase the up-time of your slurm jobs are running.

# How it works
The keepalive runtime keeps a record of jobs that are to be kept alive.
One can register/deregister a running job with keepalive by using `keepalive add/remove`. 
The attribute identifying jobs in slurm records is its name (or name prefix, if the `--startswith` flag is used).
The object used to differentiate between jobs that were successfully completed as opposed to the jobs that died/failed/were killed is a file called indicator.
It is the responsibility of the job to create the indicator file upon its successful completion (i.e. you need to modify your code to create some special file e.g. `.DONE` if the job exits ordinarily once done).

Every `--interval`-many minutes, keepalive uses `sacct` to poll slurm for the names of jobs that are either running or pending.
For every job to be kept alive:
 - If the name/name prefix is found in `sacct`, all is good and so no action is taken.
 - If the name/name prefix is not found in `sacct` and no finish indicator is present, the restart `--command` specified upon the registration of the job with keepalive is run to relaunch the job.
 - If the name/name prefix is not found in `sacct` but a finish indicator is present, no slurm action is taken and keepalive only marks the job internally as finished. It will no longer be considered in the next round of keepalive enforcement.

All jobs registered with keepalive and not removed can be listed with `keepalive list_all`. `keepalive list_finished` and `keepalive list_unfinished` can be further used to list only those that have finished/have not yet finished, respectively.
If one notices that a job has died and they do not with to wait until the next `keepalive` enforcement round is triggered (which can take as long as `--interval`-many minutes in the worst case), one can order an immediate relaunch of the job with `keepalive relaunch`.
For convenience and assuming that the command to launch the job for the first time is identical to the relaunch command, one can use `keepalive launch` to perform both the launch and `keepalive add` at the same time.
Similarly, for convenience, one can use `keepalive cancel` to both `scancel` the running job and `keepalive remove` it from keepalive tracking.

`keepalive create_indicator` and `keepalive delete_indicator` can be used for convenience/debugging.
Similarly, `keepalive set_as_finished` and `keepalive set_as_unfinished` can be used to alter the `finished` state of a job in the keepalive's records.
Note that to continue a job that has exited ordinarily, one would need to both `keepalive set_as_unfinished` and `keepalive delete_indicator` before waiting for the next keepalive enforecement round or `keepalive relaunch`ing immediately.

See `keepalive --help` for the detailed list of parameters.


## Installation
Let `KAL` be an environemtn variable that points to the directory where keepalive is to be installed, e.g.
```
export KAL=/lustre/fsw/portfolios/nvr/users/pbelcak/keepalive
```

Do
```
cd $KAL
git clone XXX
```

Add a few useful aliases to `~/.bashrc` (modify `--interval` to change the frequency of enforcement rounds)
```
export KAL=...
export KEEPALIVE_DB_PATH=$KAL/keepalive.db
alias keepalive_start="( python $KAL/keepalive.py run --interval=10 --verbosity=3 > $KAL/keepalive.log & )"
alias keepalive_kill="ps -xaf | grep keepalive.py | tail -n 1 | awk '{print $1}' | xargs kill"
alias keepalive="python $KAL/keepalive.py"
```

To build the `keepalive.db` database file, we need to start keepalive for the first time.
```
source ~/.bashrc
keepalive_start
keepalive_kill
```

And you're all set.

## Usage
```
usage: keepalive.py [-h] [--interval INTERVAL] [--name NAME] [--startswith] [--indicator INDICATOR] [--command COMMAND] [--slurm_max_name_length SLURM_MAX_NAME_LENGTH]
                    [--verbosity VERBOSITY]
                    {run,launch,add,remove,cancel,relaunch,create_indicator,delete_indicator,list_all,list_finished,list_unfinished,set_as_finished,set_as_unfinished}

Slurm Keepalive Utility

positional arguments:
  {run,launch,add,remove,cancel,relaunch,create_indicator,delete_indicator,list_all,list_finished,list_unfinished,set_as_finished,set_as_unfinished}
                        action to perform

optional arguments:
  -h, --help            show this help message and exit
  --interval INTERVAL   interval in minutes
  --name NAME, -n NAME  slurm name (or naem prefix if the --startswith flag is used) to launch/add to keepalive/remove from keepalive/cancel/relaunch-now
  --startswith          whether to match the job name with the start of the job name in the database or only accept exact name match
  --indicator INDICATOR, -i INDICATOR
                        path to the indicator file that, if exists, indicates that the job has finished ordinarily and does not need to be kept alive.
  --command COMMAND, -c COMMAND
                        command to run to relaunch the job
  --slurm_max_name_length SLURM_MAX_NAME_LENGTH
                        maximum length of the job name in slurm to be assumed by this utility
  --verbosity VERBOSITY, -v VERBOSITY
                        verbosity level
```

### A note on verbosity
Use verbosity 3 to see everything, including the `stdout` of the `--command`s when run.
Use verbosity 2 to get a listing of all actions taken and all jobs visited/checked/under monitoring.
Use verbosity 1 to get only a listing of actions as they are being taken (e.g. without the logs per job monitored).
Verbosity 0 mutes all non-error outputs.


## Some vanilla usage
```
# launch a background monitoring script with logging output to keepalive.log
( python -u keepalive.py run --interval=10 --verbosity=3 > keepalive.log & )

# if you need to kill it, use the following to find the pid
ps -axf | grep keepalive
kill pid # replace pid with the actual pid

# to launch a test job
python keepalive.py launch --name=testj0b --indicator=./out/.DONE --command="./cluster/run_cpu_job.sh testj0b" --startswith

# to cancel the test job
python keepalive.py cancel --name=testj0b
```