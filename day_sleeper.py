"""
A simple support script; sleeps for a day waking up every minute, then exits.
"""

import time

for minute in range(60 * 24):
    time.sleep(60)
    print(f"Minute {minute}: still alive")
