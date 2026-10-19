"""Run a pipeline stage as an AWS Glue job.

Glue starts ``glue/nyc_lake_job.py`` with the job's default arguments plus the ones
given for the run, all as ``--name value`` pairs mixed in with Glue's own (``--JOB_NAME``,
``--TempDir`` and so on). This module picks out the pipeline's arguments, turns the
lake settings into the ``NYC_LAKE_*`` environment the CLI reads, and runs the same
``nyc-lake`` command a laptop would.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from nyc_taxi_lake import cli

STAGES = ("clean", "model", "quality")


@dataclass(frozen=True)
class GlueRun:
    env: dict[str, str]
    argv: list[str]


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="nyc_lake_job", add_help=False)
    p.add_argument("--stage", required=True, choices=STAGES)
    p.add_argument("--start", required=True, help="first month, YYYY-MM")
    p.add_argument("--end", help="last month, YYYY-MM (default: start)")
    p.add_argument("--lake-root", required=True, help="s3://bucket the lake lives in")
    p.add_argument("--taxi-type", default="yellow")
    p.add_argument("--alert-sink", choices=["log", "sns"], default="log")
    p.add_argument("--sns-topic-arn")
    return p


def parse(argv: Sequence[str]) -> GlueRun:
    """Translate Glue's job arguments into an environment and ``nyc-lake`` argv."""
    known, _glue_own = _parser().parse_known_args(list(argv))

    env = {"NYC_LAKE_ROOT": known.lake_root, "NYC_LAKE_TAXI_TYPE": known.taxi_type}
    # An empty master leaves the session to Glue's cluster instead of local[*].
    args = [known.stage, known.start, known.end or known.start, "--master", ""]
    if known.stage == "quality":
        args += ["--alert-sink", known.alert_sink]
        if known.sns_topic_arn:
            args += ["--sns-topic-arn", known.sns_topic_arn]
    return GlueRun(env=env, argv=args)


def run(argv: Sequence[str], main: Callable[[Sequence[str] | None], int] = cli.main) -> int:
    """Set the lake environment and run the stage. Returns the CLI's exit code."""
    job = parse(argv)
    os.environ.update(job.env)
    return main(job.argv)
