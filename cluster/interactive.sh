# launch a background monitoring script with logging output to keepalive.log
( python -u keepalive.py run --interval=10 > keepalive.log & )

# if you need to kill it, use the following to find the pid
ps -axf | grep keepalive
kill pid # replace pid with the actual pid

# to launch a test job
python keepalive.py launch --name=testj0b --indicator=./out/.DONE --command="./cluster/run_cpu_job.sh testj0b" --startswith

# to cancel the test job
python keepalive.py cancel --name=testj0b

# to relaunch the test job (must not have been removed/cancelled; otherwise the database entry is gone)
python keepalive.py relaunch --name=testj0b

