"""AWS Glue entry script for the clean, model, quality and load jobs.

Terraform uploads this file to the artifacts bucket. Glue installs the nyc-taxi-lake
wheel through --additional-python-modules before running it, so all the logic lives in
the package and is tested there (see nyc_taxi_lake.glue_entry).
"""

import sys

from nyc_taxi_lake.glue_entry import run

sys.exit(run(sys.argv[1:]))
