"""Measured optional NumPy CPU / PyTorch CUDA score-grid experiment.

No model training or runtime backend switch. Both methods use float64 and the
same finite Poisson grid, including transfer time in end-to-end GPU latency.
"""
from datetime import datetime, timezone
from statistics import median
from time import perf_counter


def benchmark() -> dict:
    import numpy as np
    import torch
    report = {'created_at': datetime.now(timezone.utc).isoformat(),
              'numpy': np.__version__, 'torch': torch.__version__,
              'workload': 'BATCHED_INDEPENDENT_POISSON_SCORE_GRID_TO_HDA',
              'dtype': 'float64', 'max_goals': 12, 'repeats': 3, 'results': [],
              'production_backend_changed': False}
    if not torch.cuda.is_available():
        return dict(report, status='BLOCKED', reason='GPU_FAILURE: CUDA unavailable')
    report['device'] = torch.cuda.get_device_name(0)
    start = perf_counter()
    torch.zeros(1, device='cuda', dtype=torch.float64).sum().item()
    torch.cuda.synchronize()
    report['cuda_first_operation_seconds'] = perf_counter() - start
    k = 13
    mask_home = np.greater.outer(np.arange(k), np.arange(k))
    mask_draw = np.eye(k, dtype=bool)
    mask_away = np.less.outer(np.arange(k), np.arange(k))
    masks = (mask_home, mask_draw, mask_away)

    def cpu(rates):
        home, away = np.empty((len(rates), k)), np.empty((len(rates), k))
        home[:, 0], away[:, 0] = np.exp(-rates[:, 0]), np.exp(-rates[:, 1])
        for index in range(1, k):
            home[:, index] = home[:, index - 1] * rates[:, 0] / index
            away[:, index] = away[:, index - 1] * rates[:, 1] / index
        matrix = home[:, :, None] * away[:, None, :]
        values = np.stack([matrix[:, mask].sum(axis=1) for mask in masks], axis=1)
        return values / values.sum(axis=1, keepdims=True)

    gpu_masks = [torch.from_numpy(mask).to('cuda') for mask in masks]

    def device_kernel(rates):
        home = torch.empty((len(rates), k), device='cuda', dtype=torch.float64)
        away = torch.empty_like(home)
        home[:, 0], away[:, 0] = torch.exp(-rates[:, 0]), torch.exp(-rates[:, 1])
        for index in range(1, k):
            home[:, index] = home[:, index - 1] * rates[:, 0] / index
            away[:, index] = away[:, index - 1] * rates[:, 1] / index
        matrix = home[:, :, None] * away[:, None, :]
        values = torch.stack([matrix[:, mask].sum(dim=1) for mask in gpu_masks], dim=1)
        return values / values.sum(dim=1, keepdim=True)

    rng = np.random.default_rng(314)
    for size in (1, 256, 4096, 32768):
        rates = rng.uniform(0.2, 3.5, size=(size, 2))
        reference = cpu(rates)
        device_rates = torch.from_numpy(rates).to('cuda')
        with torch.no_grad():
            device_kernel(device_rates)
            torch.cuda.synchronize()
            cpu_times, end_to_end, device_times = [], [], []
            torch.cuda.reset_peak_memory_stats()
            for _ in range(3):
                start = perf_counter(); cpu(rates); cpu_times.append(perf_counter() - start)
                start = perf_counter()
                result = device_kernel(torch.from_numpy(rates).to('cuda')).cpu().numpy()
                torch.cuda.synchronize()
                end_to_end.append(perf_counter() - start)
                start = perf_counter(); device_kernel(device_rates); torch.cuda.synchronize()
                device_times.append(perf_counter() - start)
        error = float(np.max(np.abs(reference - result)))
        passed = bool(np.allclose(reference, result, atol=1e-12, rtol=0))
        report['results'].append({'batch_size': size, 'cpu_median_seconds': median(cpu_times),
            'gpu_end_to_end_median_seconds': median(end_to_end),
            'gpu_device_only_median_seconds': median(device_times),
            'gpu_transfer_overhead_estimate_seconds': max(0, median(end_to_end) - median(device_times)),
            'speedup_including_transfers': median(cpu_times) / median(end_to_end),
            'gpu_peak_allocated_bytes': torch.cuda.max_memory_allocated(),
            'cpu_matrix_bytes_estimate': size * k * k * 8, 'maximum_probability_difference': error,
            'correctness_passed': passed, 'winner': 'GPU' if median(end_to_end) < median(cpu_times) else 'CPU'})
    report['status'] = 'COMPLETE' if all(row['correctness_passed'] for row in report['results']) else 'BLOCKED'
    report['limitation'] = 'Three timing repeats on one machine; no model-accuracy advantage or general GPU superiority.'
    return report
