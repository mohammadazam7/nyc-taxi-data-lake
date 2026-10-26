# 0003. Quarantine rejected rows with a reason code

**Status:** Accepted

## Context

TLC files contain duplicates, negative amounts, dropoffs before pickups, trips outside
the file's month and unknown zones. Dropping these rows silently hides how much data was
lost and why, and makes it impossible to tell a source problem from a bug in the rules.

## Decision

The clean stage writes every rejected row to a quarantine zone, partitioned by month,
tagged with the first rule it breaks from a fixed set of reason codes. The run summary
records counts per code. The quality suite checks that raw rows equal clean plus
quarantined rows and that the quarantine rate stays below a threshold.

## Consequences

- Row counts reconcile exactly across zones, so a lost row is a detectable failure.
- A change in the source, such as a new defect pattern, shows up as a shift in reason-code
  counts rather than as a quiet drop in volume.
- The reason codes become part of the data contract; renaming one is a breaking change.
- Quarantine storage grows with the source; a lifecycle rule expires it.
