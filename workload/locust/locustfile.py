"""Locust load for the 4 workload patterns: steady 500, daily cycle, 10x spike,
steady growth. Pick a pattern with env PATTERN; run against the nginx address.

  PATTERN=steady   locust -f locustfile.py -H http://localhost:8090
  PATTERN=spike    locust -f locustfile.py -H http://localhost:8090
  PATTERN=cycle    CYCLE_S=600 locust -f locustfile.py -H http://localhost:8090
  PATTERN=growth   locust -f locustfile.py -H http://localhost:8090

Each user does ~1 req per cycle (light x5 + compute + download), so users ≈
target_rpm / 60 * cycle_seconds. BASE_USERS/PEAK_USERS env vars tune it.
"""
import math
import os
import time

from locust import Shape, User, constant, task

PATTERN = os.environ.get("PATTERN", "steady")
BASE_USERS = int(os.environ.get("BASE_USERS", "25"))
PEAK_USERS = int(os.environ.get("PEAK_USERS", "250"))  # ≈ steady 500 rpm
CYCLE_S = int(os.environ.get("CYCLE_S", "600"))
START_T = time.time()


class WorkloadUser(User):
    wait_time = constant(1)

    @task(5)
    def light(self):
        self.client.get("/")

    @task(1)
    def heavy(self):
        self.client.get("/compute?n=1500000")

    @task(1)
    def big(self):
        self.client.get("/download?kb=4096")


class PatternShape(Shape):
    users = 0

    def shape(self):
        while True:
            t = time.time() - START_T
            if PATTERN == "steady":
                users, spawn = PEAK_USERS, PEAK_USERS
            elif PATTERN == "cycle":
                # sine wave between BASE and PEAK over one CYCLE_S day-cycle
                phase = 2 * math.pi * (t % CYCLE_S) / CYCLE_S
                users = int(BASE_USERS + (PEAK_USERS - BASE_USERS) * (0.5 + 0.5 * math.sin(phase)))
                spawn = max(1, users - self.users)
            elif PATTERN == "spike":
                # 10x spike: BASE for 60 s, jump to PEAK for 120 s, back to BASE
                users = PEAK_USERS if 60 <= t % 300 <= 180 else BASE_USERS
                spawn = PEAK_USERS
            elif PATTERN == "growth":
                # steady growth: +BASE_USERS every 30 s, capped at PEAK
                users = min(PEAK_USERS, BASE_USERS + BASE_USERS * int(t // 30))
                spawn = max(1, users - self.users)
            else:
                raise SystemExit(f"unknown PATTERN {PATTERN!r} (steady|cycle|spike|growth)")
            self.users = users
            yield users, spawn
