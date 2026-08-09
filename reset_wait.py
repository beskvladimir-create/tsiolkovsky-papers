#!/usr/bin/env python3
"""
How long to wait for the subscription's session limit to lift.

The limit that stops a nightly run is the five-hour session window, not the
week's, and the reply that announces it says when it goes away: "You've hit
your session limit · resets 1am". Treating that as a reason to stop wastes
whatever is left of the night. On 8 August the run stopped at 00:34 for a limit
that lifted at 01:00 and never came back, losing three hours of a six-hour
window.

Reads the model's reply on standard input, prints the number of seconds to
wait, and prints 0 when there is nothing sensible to wait for. Two hours is the
ceiling: a longer wait means this is not the session limit, and sitting on it
would only burn the night differently.

    echo "$RESP" | python3 reset_wait.py
"""
import datetime
import re
import sys

MAX_WAIT = 2 * 3600


def seconds_until(reply, now=None):
    now = now or datetime.datetime.now()
    m = re.search(r"resets?\s+(\d{1,2})\s*(am|pm)", reply, re.I)
    if not m:
        return 0
    hour = int(m.group(1)) % 12 + (12 if m.group(2).lower() == "pm" else 0)
    # A minute past the hour, so the window is certainly open by then.
    target = now.replace(hour=hour, minute=1, second=0, microsecond=0)
    if target <= now:
        target += datetime.timedelta(days=1)
    wait = int((target - now).total_seconds())
    return wait if wait <= MAX_WAIT else 0


if __name__ == "__main__":
    print(seconds_until(sys.stdin.read()))
