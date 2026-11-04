"""Safe, allocation-free capacity planning for project-owned dense models.

All performance inputs are hypothetical; reports are not benchmark results.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from scripts.plan_100b import ROOT, estimate


def resources(model: dict, tokens_per_parameter: int = 20, *,
              device_memory_gb: float = 80, usable_fraction: float = 0.8,
              aggregate_flops_per_second: float | None = None) -> dict:
    for name, value in [('device_memory_gb', device_memory_gb),
                        ('usable_fraction', usable_fraction)]:
        if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
            raise ValueError(f'{name} must be positive and finite')
    if usable_fraction > 1:
        raise ValueError('usable_fraction must be at most 1')
    report = estimate(model, tokens_per_parameter)
    capacity = device_memory_gb * 1_000_000_000 * usable_fraction
    report['hypothetical_memory_scenario'] = {
        'device_memory_gb_decimal': device_memory_gb,
        'usable_fraction': usable_fraction,
        'bf16_weight_shards_minimum': math.ceil(report['bf16_weights_bytes'] / capacity),
        'adam_state_shards_minimum': math.ceil(
            report['mixed_precision_adam_state_bytes_lower_bound'] / capacity),
        'warning': 'Memory-only lower bounds, not a runnable device count; excludes activations and communication.'
    }
    if aggregate_flops_per_second is not None:
        if (isinstance(aggregate_flops_per_second, bool)
                or not math.isfinite(aggregate_flops_per_second)
                or aggregate_flops_per_second <= 0):
            raise ValueError('aggregate_flops_per_second must be positive and finite')
        report['hypothetical_compute_scenario'] = {
            'assumed_sustained_aggregate_flops_per_second': aggregate_flops_per_second,
            'idealized_days': report['training_flops_approx_6ND'] / aggregate_flops_per_second / 86400,
            'warning': 'User-supplied throughput, not measured; excludes downtime and other overheads.'
        }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'configs/rayan-1t.json')
    parser.add_argument('--device-memory-gb', type=float, default=80)
    parser.add_argument('--usable-fraction', type=float, default=0.8)
    parser.add_argument('--aggregate-flops-per-second', type=float)
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text())
        report = resources(config['model'], config['tokens_per_parameter'],
                           device_memory_gb=args.device_memory_gb,
                           usable_fraction=args.usable_fraction,
                           aggregate_flops_per_second=args.aggregate_flops_per_second)
    except (ValueError, KeyError, OSError, TypeError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
