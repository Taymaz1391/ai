"""Allocation-free capacity estimate; never loads or initializes model weights."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def estimate(model: dict, tokens_per_parameter: int = 20) -> dict:
    keys = ('vocab_size', 'block_size', 'n_layer', 'n_head', 'n_embd')
    for key in keys:
        if type(model[key]) is not int or model[key] <= 0:
            raise ValueError(f'{key} must be a positive integer')
    c = model['n_embd']
    if c % model['n_head']:
        raise ValueError('Embedding width must be divisible by head count')
    if type(tokens_per_parameter) is not int or tokens_per_parameter <= 0:
        raise ValueError('tokens_per_parameter must be a positive integer')
    # Exact for param_shapes in rayan.model: tied token embeddings, learned
    # positions, two affine layer norms per block, standard 4C GELU MLP.
    parameters = ((model['vocab_size'] + model['block_size']) * c + 2 * c
                  + model['n_layer'] * (12 * c * c + 13 * c))
    tokens = parameters * tokens_per_parameter
    return {
        'status': 'plan_only_not_trained',
        'parameters': parameters,
        'target_training_tokens_heuristic': tokens,
        'training_flops_approx_6ND': 6 * parameters * tokens,
        'bf16_weights_bytes': 2 * parameters,
        'fp32_weights_bytes': 4 * parameters,
        'mixed_precision_adam_state_bytes_lower_bound': 16 * parameters,
        'caveats': [
            'Memory excludes activations, attention, buffers and communication.',
            'Current NumPy implementation uses FP32, not BF16 distributed training.',
            'Token budget is a planning heuristic, not a quality guarantee.',
            'No training, deployment or benchmark is claimed by this report.'
        ]
    }


if __name__ == '__main__':
    config = json.loads((ROOT / 'configs/rayan-100b.json').read_text())
    print(json.dumps(estimate(config['model'], config['tokens_per_parameter']), indent=2))
