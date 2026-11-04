"""Configuration for the capacity and cost engine.

Stores configurable thresholds, instance candidates, current deployment
settings, and provisional capacity assumptions.
"""

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

# Pricing region settings.
AWS_REGION_CODE = "ap-south-1"
AWS_REGION_NAME = "Asia Pacific (Mumbai)"
AWS_OS = "Linux"
AWS_TENANCY = "Shared"
AWS_PURCHASE_MODEL = "On-Demand"
AWS_CURRENCY = "USD"

# Safety margin for instance count formula.
SAFETY_MARGIN_INSTANCES = 1
