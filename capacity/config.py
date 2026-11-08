"""Configuration for the capacity and cost engine.

Stores configurable thresholds, instance candidates, current deployment
settings, and provisional capacity assumptions.
"""
from typing import Optional

# Target CPU utilisation for capacity sizing.
DEFAULT_CPU_TARGET_PCT = 70.0
CPU_TARGET_OPTIONS = [60.0, 70.0, 80.0]

# Instance families and candidate types for scale-up comparisons.
INSTANCE_FAMILIES = ["t3", "t4g", "m6i", "c6i"]

# Configured candidate instance types (must include current and larger types).
CANDIDATE_INSTANCE_TYPES = [
    "t3.micro",
    "t3.small",
    "t3.medium",
    "t3.large",
    "t3.xlarge",
    "t4g.micro",
    "t4g.small",
    "t4g.medium",
    "t4g.large",
    "m6i.large",
    "m6i.xlarge",
    "m6i.2xlarge",
    "c6i.large",
    "c6i.xlarge",
    "c6i.2xlarge",
]

# Provisionally configured relative capacity multipliers for larger instances
# when measured capacity is unavailable. These are NOT measured AWS performance.
# They must be replaced with Member 1 measurements in Phase III.
PROVISIONAL_CAPACITY_MULTIPLIER = {
    "t3.micro": 1.0,
    "t3.small": 2.0,
    "t3.medium": 3.0,
    "t3.large": 4.0,
    "t3.xlarge": 8.0,
    "t4g.micro": 1.0,
    "t4g.small": 2.0,
    "t4g.medium": 3.0,
    "t4g.large": 4.0,
    "m6i.large": 4.0,
    "m6i.xlarge": 8.0,
    "m6i.2xlarge": 16.0,
    "c6i.large": 4.0,
    "c6i.xlarge": 8.0,
    "c6i.2xlarge": 16.0,
}

# Default current deployment assumption.
DEFAULT_CURRENT_INSTANCE_TYPE = "t3.micro"
DEFAULT_CURRENT_INSTANCES = 1

# Measured CPU coefficient from real AWS run (Member 1, 2026-11-04):
# cluster CPU ≈ 2.7% per 100 rpm (burst credits) — NOT for sustained sizing
MEASURED_CPU_PCT_PER_100_RPM_BURST = 2.7

# Sustained CPU coefficient (burst credits exhausted, free plan unlimited mode blocked):
# Nov-5 run: ~8% per 100 rpm once credits are gone. Use this for planning.
MEASURED_CPU_PCT_PER_100_RPM_SUSTAINED = 8.0

# Default to sustained for conservative planning (credits always run out on free plan)
MEASURED_CPU_PCT_PER_100_RPM = MEASURED_CPU_PCT_PER_100_RPM_SUSTAINED

# Memory binding limits - OOM RPM = 620 rpm per GB of RAM.
# Derived from real AWS run: t3.micro (1 GB) OOMs at ~620 rpm.
# These are provisional until Member 1 provides measured capacity per instance type.
OOM_RPM_PER_GB = 620

# RAM (GB) for each candidate instance type
INSTANCE_RAM_GB = {
    "t3.micro": 1.0,
    "t3.small": 2.0,
    "t3.medium": 4.0,
    "t3.large": 8.0,
    "t3.xlarge": 16.0,
    "t4g.micro": 1.0,
    "t4g.small": 2.0,
    "t4g.medium": 4.0,
    "t4g.large": 8.0,
    "t4g.xlarge": 16.0,
    "m6i.large": 8.0,
    "m6i.xlarge": 16.0,
    "m6i.2xlarge": 32.0,
    "c6i.large": 8.0,
    "c6i.xlarge": 16.0,
    "c6i.2xlarge": 32.0,
}

# Memory binding limit for t3.micro (real AWS run):
# OOM at ~620 rpm per instance — RAM is binding constraint, not CPU
T3_MICRO_OOM_RPM = 620

# Memory binding limits for t3 family (extrapolated from t3.micro 1 GB = 620 rpm).
# These are provisional until Member 1 provides measured capacity per instance type.
# Formula: OOM_RPM = 620 * (instance_memory_gb / 1.0)
T3_OOM_RPM = {
    "t3.micro": 620,      # 1 GB
    "t3.small": 1240,     # 2 GB
    "t3.medium": 2480,    # 4 GB
    "t3.large": 4960,     # 8 GB
    "t3.xlarge": 9920,    # 16 GB
}

def get_oom_rpm(instance_type: str) -> Optional[int]:
    """Get OOM RPM limit for an instance type based on its RAM."""
    ram_gb = INSTANCE_RAM_GB.get(instance_type)
    if ram_gb is None:
        return None
    return int(OOM_RPM_PER_GB * ram_gb)

# Pricing region settings.
AWS_REGION_CODE = "ap-south-1"
AWS_REGION_NAME = "Asia Pacific (Mumbai)"
AWS_OS = "Linux"
AWS_TENANCY = "Shared"
AWS_PURCHASE_MODEL = "On-Demand"
AWS_CURRENCY = "USD"

# Safety margin for instance count formula.
SAFETY_MARGIN_INSTANCES = 1
