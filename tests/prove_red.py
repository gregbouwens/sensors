#!/usr/bin/env python3
"""Mutation check: prove the load-bearing tests actually fail when broken.

A test that has never been seen failing may be passing for the wrong reason.
This applies one surgical mutation at a time to the production code, runs the
test that is supposed to catch it, and restores the file. A mutation that
survives means that test is decorative.

Not part of the pytest suite (pytest only collects test_*.py) and not run in
CI -- it rewrites source files, so it is a deliberate, local verification step.

    .venv/bin/python3 tests/prove_red.py
"""

import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent

MUTATIONS = [
    (
        "carry-forward watermark: failed run resets last_success",
        "aranet/metrics.py",
        "    last_success = now if run.succeeded else previous_success",
        "    last_success = now  # MUTANT: always stamp, losing the watermark",
        "tests/test_metrics.py::test_failed_run_carries_forward_the_previous_success_timestamp",
    ),
    (
        "fresh deploy: emit 0 instead of omitting the watermark",
        "aranet/metrics.py",
        "    if last_success is not None:\n        lines.append(_metric(METRIC_LAST_SUCCESS, last_success))",
        "    lines.append(_metric(METRIC_LAST_SUCCESS, last_success or 0.0))  # MUTANT",
        "tests/test_metrics.py::test_failed_run_with_no_prior_success_omits_the_watermark",
    ),
    (
        "2026-08-03 regression: connection errors not retryable",
        "aranet/sink.py",
        "INFLUX_RETRYABLE_ERRORS = (InfluxDBError, urllib3.exceptions.HTTPError, OSError)",
        "INFLUX_RETRYABLE_ERRORS = (InfluxDBError,)  # MUTANT: the pre-fix behaviour",
        "tests/test_retry.py::test_connection_errors_are_retried",
    ),
    (
        "data continuity: co2 written as float instead of int",
        "aranet/sink.py",
        "        .field(FIELD_CO2, int(reading.co2_ppm))",
        "        .field(FIELD_CO2, float(reading.co2_ppm))  # MUTANT",
        "tests/test_sink.py::test_point_schema_is_unchanged_by_the_refactor",
    ),
    (
        "exit-code contract: influx failure reported as sensor failure",
        "aranet/job.py",
        "            exit_code = EXIT_INFLUX_WRITE_FAILED",
        "            exit_code = EXIT_SENSOR_READ_FAILED  # MUTANT",
        "tests/test_job.py::test_an_influx_failure_exits_three_and_records_a_good_sensor_read",
    ),
    (
        "metrics always published, even on total failure",
        "aranet/job.py",
        "    metrics.write(",
        "    _skip = metrics.write if False else (lambda *a, **k: None)\n    _skip(",
        "tests/test_job.py::test_a_run_emits_metrics_even_when_everything_fails",
    ),
    (
        "atomic write leaves no temp files",
        "aranet/metrics.py",
        "        os.replace(temp_path, target)  # atomic; node_exporter never sees a torn file",
        "        import shutil; shutil.copyfile(temp_path, target)  # MUTANT: non-atomic",
        "tests/test_metrics.py::test_write_is_atomic_and_leaves_no_temp_files",
    ),
]


def main():
    survivors = []
    for label, rel_path, original, mutant, test in MUTATIONS:
        path = REPO / rel_path
        source = path.read_text()
        if original not in source:
            print(f"SKIP  {label}\n      anchor no longer present in {rel_path}")
            survivors.append(label)
            continue

        path.write_text(source.replace(original, mutant, 1))
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", test, "-q", "--no-header"],
                cwd=REPO, capture_output=True, text=True,
            )
        finally:
            path.write_text(source)

        caught = result.returncode != 0
        print(f"{'RED  ' if caught else 'GREEN'} {label}")
        if not caught:
            print("      ^^ mutation survived -- this test is not testing what it claims")
            survivors.append(label)

    print()
    if survivors:
        print(f"{len(survivors)} mutation(s) survived:")
        for label in survivors:
            print(f"  - {label}")
        return 1
    print(f"All {len(MUTATIONS)} mutations were caught. Tests verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
