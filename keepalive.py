import argparse
import sqlite3

import subprocess
import os

from datetime import datetime
from time import sleep

argparser = argparse.ArgumentParser(description='Slurm Keepalive Utility')
argparser.add_argument('action', type=str, help='action to perform', choices=['run', 'launch', 'add', 'remove', 'cancel', 'relaunch', 'create_indicator', 'delete_indicator', 'list_all', 'list_finished', 'list_unfinished', 'set_as_finished', 'set_as_unfinished'])
argparser.add_argument('--interval', type=int, help='interval in minutes', default=None)
argparser.add_argument('--name', '-n', type=str, help='slurm name (or naem prefix if the --startswith flag is used) to launch/add to keepalive/remove from keepalive/cancel/relaunch-now', default=None)
argparser.add_argument('--startswith', help='whether to match the job name with the start of the job name in the database or only accept exact name match', action='store_true')
argparser.add_argument('--indicator', '-i', type=str, help='path to the indicator file that, if exists, indicates that the job has finished ordinarily and does not need to be kept alive.', default=None)
argparser.add_argument('--command', '-c', type=str, help='command to run to relaunch the job', default=None)
argparser.add_argument('--slurm_max_name_length', type=int, help='maximum length of the job name in slurm to be assumed by this utility', default=256)
argparser.add_argument('--verbosity', '-v', type=int, help='verbosity level', default=2)
args = argparser.parse_args()

db_path = os.environ.get('KEEPALIVE_DB_PATH', 'keepalive.db')
if args.verbosity > 2:
    print(f'Current working directory: {os.getcwd()}')
    print(f'Database path: {db_path}')


def run(args):
    run_startup(args)
    while True:
        keepalive(args)
        sleep(args.interval * 60)

def run_startup(args):
    if args.interval is None:
        raise ValueError('Interval (an integer of minutes) must be specified when running `keepalive run` action')

    # if the db file does not exist, create it
    if not os.path.exists(db_path):
        if args.verbosity > 0:
            print(f'Database file {db_path} does not exist; creating it')
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute('CREATE TABLE jobs (name text, indicator text, command text, added integer, last_relaunch integer, last_check integer, finished integer, startswith integer)')
        conn.commit()
        conn.close()

def keepalive(args):
    # get all jobs that have finished > 0 in the table jobs of the database
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('SELECT name, indicator, command, startswith FROM jobs WHERE finished = 0')
    jobs = c.fetchall()
    conn.close()

    if args.verbosity > 0:
        # print the timestamp
        print('-' * 10 + '> ' + datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        print(f'Running keepalive routine; tracking {len(jobs)} unfinished jobs')

    name_to_job_id = get_running_jobs()
    if args.verbosity > 1:
        print(f'Jobs that are currently running or pending:')
        for name, job_id in name_to_job_id.items():
            print(f' - {job_id}: {name}')

    # for each job, check if the indicator file exists
    # if it does, set the job as finished
    # if it does not, check if the job is running
    # if it is not running, relaunch the job
    for job in jobs:
        name = job[0]
        indicator = job[1]
        command = job[2]
        startswith = job[3]

        if args.verbosity > 1:
            print(f'-> checking for the indicator of {name} (startswith {startswith}, indicator path "{indicator}")')

        if os.path.exists(indicator):
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            c.execute('UPDATE jobs SET finished = 1 WHERE name = ?', (name,))
            conn.commit()
            conn.close()

            if args.verbosity > 1:
                print(f'   job {name} has the finish indicator present; setting finished flag to 1')
        else:
            # if the job is running, update the last_check
            job_id: int = find_job_id(name, startswith, name_to_job_id)
            if job_id != -1:
                conn = sqlite3.connect(db_path)
                c = conn.cursor()
                c.execute('UPDATE jobs SET last_check = ? WHERE name = ?', (datetime.now(), name))
                conn.commit()
                conn.close()

                if args.verbosity > 1:
                    print(f'   job {name} (startswith={startswith}) is running/pending and finish indicator is not present')
                    print(f'   updated {name} last_check')
            else:
                # if the job is not running, relaunch it
                conn = sqlite3.connect(db_path)
                c = conn.cursor()
                c.execute('UPDATE jobs SET last_relaunch = ? WHERE name = ?', (datetime.now(), name))
                conn.commit()
                conn.close()

                if args.verbosity > 1:
                    print(f'   job {name} (startswith={startswith}) is not running/pending and finish indicator is not present; relaunching it by running "{command}"')
                    print(f'   updated {name} last_relaunch')
                
                sp = subprocess.run(command, shell=True, capture_output=True)
                if args.verbosity > 2:
                    print(sp.stdout.decode())

    print('Keepalive routine finished')
    
def get_running_jobs():
    # use subprocess.run to run the command `sacct --format="JobID,JobName%50"` and read the output
    sacct_call = subprocess.run(['sacct', f'--format=JobID,JobName%{args.slurm_max_name_length},State'], capture_output=True)
    # read the stdout of the command and split it by newline
    lines = sacct_call.stdout.decode().split('\n')
    # each line contains the job_id (integer) and the name (string)
    # we need to build a dict of name -> job_id
    name_to_job_id = {}
    for line in lines:
        if len(line) == 0:
            continue
        line_parts = line.split()
        
        if len(line_parts) < 3:
            continue
        if line_parts[2] != 'RUNNING' and line_parts[2] != 'PENDING':
            continue
        try:
            job_id = int(line_parts[0])
        except ValueError:
            continue
        
        name = line_parts[1]
        name_to_job_id[name] = job_id
    
    return name_to_job_id

def add(args):
    # check if name, indicator, command are not None
    if args.name is None:
        raise ValueError('Job name must be specified when adding a job to keepalive')

    if args.indicator is None:
        raise ValueError('Indicator file path must be specified when adding a job to keepalive')
    
    if args.command is None:
        raise ValueError('Command to run must be specified when adding a job to keepalive')

    # check if the job name is not longer than the maximum length of the job name in Slurm
    if len(args.name) > args.slurm_max_name_length:
        raise ValueError(f'Job name is too long. Maximum length of the job name in Slurm is {args.slurm_max_name_length}')
    
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # check if the job does not already live in the db
    c.execute('SELECT * FROM jobs WHERE name = ?', (args.name,))
    job = c.fetchone()
    if job is not None:
        raise ValueError(f'Job with name {args.name} already exists in the database')
    
    c.execute('INSERT INTO jobs (name, indicator, command, added, last_check, finished, startswith) VALUES (?, ?, ?, ?, ?, ?, ?)', (args.name, args.indicator, args.command, datetime.now(), datetime.now(), 0, int(args.startswith)))
    conn.commit()
    conn.close()

    if args.verbosity > 0:
        print(f'Job {args.name} (startswith={int(args.startswith)}) added to the database')

def launch(args):
    # check if name, indicator, command are not None
    if args.name is None:
        raise ValueError('Job name must be specified when launching a job through keepalive')
    if args.indicator is None:
        raise ValueError('Indicator file path must be specified when launching a job through keepalive')
    if args.command is None:
        raise ValueError('Command to run must be specified when launching a job through keepalive')

    # check if the job name is not longer than the maximum length of the job name in Slurm
    if len(args.name) > args.slurm_max_name_length:
        raise ValueError(f'Job name is too long. Maximum length is set to {args.slurm_max_name_length}')
    
    # use subprocess to launch the job by executing the command
    if args.verbosity > 0:
        print(f'Launching {args.name} through slurm')
    call = subprocess.run(args.command, shell=True, capture_output=True)
    if args.verbosity > 2:
        print(call.stdout.decode())

    add(args)

def remove(args) -> int:
    # check if name is not None
    if args.name is None:
        raise ValueError('Job name must be specified when removing a job from keepalive')
    
    conn = sqlite3.connect(db_path)
    
    # is a job with the specified name in the db?
    # if yes delete it, if not raise an error
    c = conn.cursor()
    c.execute('SELECT startswith FROM jobs WHERE name = ?', (args.name,))
    job = c.fetchone()
    if job is None:
        raise ValueError(f'Job {args.name} not found in the database')
    else:
        startswith = int(job[0])
    
    c.execute('DELETE FROM jobs WHERE name = ?', (args.name,))
    conn.commit()
    conn.close()

    if args.verbosity > 0:
        print(f'Job {args.name} (startswith={startswith}) removed from the database')

    return startswith

def cancel(args):
    startswith: int = remove(args)

    # get the running jobs
    name_to_job_id = get_running_jobs()
    # if the job is running, cancel it
    job_id = find_job_id(args.name, startswith == 1, name_to_job_id)
    if job_id != -1:
        if args.verbosity > 0:
            print(f'Cancelling job {args.name} (startswith={startswith}) and id {job_id}')
        sp = subprocess.run(['scancel', str(job_id)], capture_output=True)
        if args.verbosity > 0:
            print(sp.stdout.decode())
    else:
        raise ValueError(f'Job {args.name} (startswith={startswith}) is not running')

def relaunch(args):
    # check if name is a non-empty string
    if args.name is None:
        raise ValueError('Job name must be specified when relaunch a job')
    
    # check if the job name is not longer than the maximum length of the job name in Slurm
    if len(args.name) > args.slurm_max_name_length:
        raise ValueError(f'Job name is too long. Maximum length of the job name is currently set to {args.slurm_max_name_length}')

    # check if the job is in the db; if it is, get its indicator and command
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('SELECT name, indicator, command, startswith FROM jobs WHERE name = ?', (args.name,))
    job = c.fetchone()
    conn.close()

    if job is None:
        raise ValueError(f'Job {args.name} not found in the database')
    
    indicator = job[1]
    command = job[2]
    startswith = job[3]
    
    # check whether the job isn't actually still running
    name_to_job_id = get_running_jobs()
    job_id: int = find_job_id(args.name, startswith, name_to_job_id)
    if job_id != -1:
        raise ValueError(f'Job {args.name} (startswith={startswith}) is still running')

    # check if the indicator file exists
    if os.path.exists(indicator):
        raise ValueError(f'Indicator file {indicator} exists; the job has finished and does not need to be relaunched')
    
    # relaunch the job and print the output of the relaunch command
    if args.verbosity > 0:
        print(f'relaunching {args.name} through slurm')
    call = subprocess.run(command, shell=True, capture_output=True)
    if args.verbosity > 2:
        print(call.stdout.decode())

    # update the last_relaunch in the db
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('UPDATE jobs SET last_relaunch = ? WHERE name = ?', (datetime.now(), args.name))
    conn.commit()
    conn.close()

    if args.verbosity > 0:
        print(f'Updated {args.name} last_relaunch to {datetime.now()}')

def create_indicator(args):
    # check if name is not None
    if args.name is None:
        raise ValueError('Job name must be specified when creating an indicator file')
    
    conn = sqlite3.connect(db_path)
    
    # is a job with the specified name in the db?
    # if not raise an error, if yes create the indicator file
    c = conn.cursor()
    c.execute('SELECT * FROM jobs WHERE name = ?', (args.name,))
    job = c.fetchone()
    if job is None:
        conn.close()
        raise ValueError(f'Job with name {args.name} not found in the database')
    
    indicator = job[1]
    if os.path.exists(indicator):
        raise ValueError(f'Indicator file {indicator} for the job {args.name} already exists')
    else:
        if args.verbosity > 0:
            print(f'Creating indicator file {indicator} for the job {args.name}')
        with open(indicator, 'w') as f:
            f.write('')

    conn.close()

def delete_indicator(args):
    # check if name is not None
    if args.name is None:
        raise ValueError('Job name must be specified when removing a job from keepalive')
    
    conn = sqlite3.connect(db_path)
    
    # is a job with the specified name in the db?
    # if not raise an error, if yes delete the indicator file
    c = conn.cursor()
    c.execute('SELECT * FROM jobs WHERE name = ?', (args.name,))
    job = c.fetchone()
    if job is None:
        conn.close()
        raise ValueError(f'Job with name {args.name} not found in the database')
    
    indicator = job[1]
    if os.path.exists(indicator):
        if args.verbosity > 0:
            print(f'Removing indicator file {indicator} for the job {args.name}')
        os.remove(indicator)
    else:
        raise ValueError(f'Indicator file {indicator} for the job {args.name} does not exist')

def set_as(args, finished: bool):
    # check if name is not None
    if args.name is None:
        raise ValueError('Job name must be specified when setting a job as finished or unfinished')
    
    conn = sqlite3.connect(db_path)
    
    # is a job with the specified name in the db?
    # if not raise an error, if yes set the job as finished or unfinished
    c = conn.cursor()
    c.execute('SELECT * FROM jobs WHERE name = ?', (args.name,))
    job = c.fetchone()
    if job is None:
        conn.close()
        raise ValueError(f'Job with name {args.name} not found in the database')
    
    c.execute('UPDATE jobs SET finished = ? WHERE name = ?', (int(finished), args.name))
    conn.commit()
    conn.close()

    if args.verbosity > 0:
        print(f'Job {args.name} set as {"finished" if finished else "unfinished"}')

def do_list(args, what="all"):
    constraint = ""
    if what == "finished":
        constraint = " WHERE finished > 0"
    elif what == "unfinished":
        constraint = " WHERE finished = 0"

    # connect to the database and retrieve all jobs
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('SELECT name, finished, indicator, command, added, last_relaunch, last_check FROM jobs'+constraint)
    jobs = c.fetchall()
    conn.close()

    jobs = [[str(field) for field in job] for job in jobs]
    jobs.insert(0, ['name', 'finished', 'indicator', 'command', 'added', 'last_relaunch', 'last_check'])

    pretty_print_table(jobs, line_between_rows=True)

def find_job_id(name: str, startswith: bool, name_to_job_id: dict[str, int]) -> int:
    job_id: int = -1
    if startswith:
        for running_job_name, running_job_id in name_to_job_id.items():
            if running_job_name.startswith(name):
                job_id = running_job_id 
                break
    else:
        job_id = name_to_job_id.get(name, -1)
    return job_id

def pretty_print_table(rows, line_between_rows=True):
  """
  Example Output
  ┌──────┬─────────────┬────┬───────┐
  │ True │ short       │ 77 │ catty │
  ├──────┼─────────────┼────┼───────┤
  │ 36   │ long phrase │ 9  │ dog   │
  ├──────┼─────────────┼────┼───────┤
  │ 8    │ medium      │ 3  │ zebra │
  └──────┴─────────────┴────┴───────┘
  """

  # find the max length of each column
  max_col_lens = list(map(max, zip(*[(len(str(cell)) for cell in row) for row in rows])))

  # print the table's top border
  print('┌' + '┬'.join('─' * (n + 2) for n in max_col_lens) + '┐')

  rows_separator = '├' + '┼'.join('─' * (n + 2) for n in max_col_lens) + '┤'

  row_fstring = ' │ '.join("{: <%s}" % n for n in max_col_lens)

  for i, row in enumerate(rows):
    print('│', row_fstring.format(*map(str, row)), '│')
    
    if line_between_rows and i < len(rows) - 1:
      print(rows_separator)

  # print the table's bottom border
  print('└' + '┴'.join('─' * (n + 2) for n in max_col_lens) + '┘')

if __name__ == '__main__':
    try:
        if args.action == 'run':
            run(args)
        elif args.action == 'add':
            add(args)
        elif args.action == 'launch':
            launch(args)
        elif args.action == 'remove':
            remove(args)
        elif args.action == 'cancel':
            cancel(args)
        elif args.action == 'relaunch':
            relaunch(args)
        elif args.action == 'create_indicator':
            create_indicator(args)
        elif args.action == 'delete_indicator':
            delete_indicator(args)
        elif args.action == 'set_as_finished':
            set_as(args, finished=True)
        elif args.action == 'set_as_unfinished':
            set_as(args, finished=False)
        elif args.action == 'list_all':
            do_list(args, what="all")
        elif args.action == 'list_finished':
            do_list(args, what="finished")
        elif args.action == 'list_unfinished':
            do_list(args, what="unfinished")
        else:
            raise ValueError('Unknown action specified. See --help for the list of supported actions.')
    except Exception as e:
        print("Error: " + str(e))
        exit(1)
