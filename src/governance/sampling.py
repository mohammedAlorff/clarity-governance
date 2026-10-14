"""Bounded, deterministic sampling of redacted descriptors, never raw values.

Selection is from at most the first 100 candidates, not uniformly from the
whole population. MySQL candidates use primary-key ordering when available;
without a primary key, the database does not guarantee repeatable pool order.
"""

import math
import os
import random
from dataclasses import dataclass
from fractions import Fraction
from itertools import islice

_LENGTH_BOUNDS = (0, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 4096)
LENGTH_BUCKETS = (
    '0',
    '1-4',
    '5-8',
    '9-16',
    '17-32',
    '33-64',
    '65-128',
    '129-256',
    '257-512',
    '513-1024',
    '1025-4096',
    '4097+',
)


def length_bucket(length):
    """Generalize a character count into a fixed, coarse interval."""
    if type(length) is not int or length < 0:
        raise ValueError('Invalid sample length')
    for bound, label in zip(_LENGTH_BOUNDS, LENGTH_BUCKETS):
        if length <= bound:
            return label
    return LENGTH_BUCKETS[-1]


@dataclass(frozen=True)
class SamplingPolicy:
    rate: float = 0.05
    max_samples: int = 10
    seed: int = 42
    candidate_pool: int = 100

    def __post_init__(self):
        if (
            type(self.rate) not in (int, float)
            or not 0 < self.rate <= 0.1
            or not math.isfinite(self.rate)
        ):
            raise ValueError('Privacy sample rate must be greater than zero and at most 0.1')
        if type(self.max_samples) is not int or not 1 <= self.max_samples <= 10:
            raise ValueError('Privacy maximum samples must be an integer from 1 to 10')
        if type(self.seed) is not int or not 0 <= self.seed <= 2147483647:
            raise ValueError('Privacy sample seed must be an integer from 0 to 2147483647')
        if type(self.candidate_pool) is not int or not 1 <= self.candidate_pool <= 100:
            raise ValueError('Privacy candidate pool must be an integer from 1 to 100')

    @classmethod
    def from_env(cls):
        try:
            rate = float(os.environ.get('PRIVACY_SAMPLE_RATE', '0.05'))
            maximum = int(os.environ.get('PRIVACY_MAX_SAMPLES', '10'))
            seed = int(os.environ.get('PRIVACY_SAMPLE_SEED', '42'))
        except (TypeError, ValueError, OverflowError):
            raise ValueError('Invalid privacy sampling configuration') from None
        return cls(rate=rate, max_samples=maximum, seed=seed)

    def select(self, candidates, population_count, requested_limit):
        """Select redacted descriptors without reading past the bounded pool.

        The rate sets a rounded-up output budget; the candidate pool and
        absolute cap can reduce it further. It is not a population inclusion
        probability. A local RNG leaves the application's RNG state intact.
        """
        if type(population_count) is not int or population_count < 0:
            raise ValueError('Invalid sample population count')
        if type(requested_limit) is not int or not 1 <= requested_limit <= 100:
            raise ValueError('Sample limit must be an integer from 1 to 100')
        pool = list(islice(candidates, self.candidate_pool))
        # Decimal spelling avoids floating point rounding at rate boundaries
        # and integer arithmetic safely handles very large row counts.
        rate = Fraction(str(self.rate))
        budget = (population_count * rate.numerator + rate.denominator - 1) // rate.denominator
        count = min(requested_limit, self.max_samples, budget, len(pool))
        selected = random.Random(self.seed).sample(pool, count)
        return selected, {
            'strategy': 'seeded_bounded_pool',
            'candidate_count': len(pool),
            'returned_count': count,
            'population_count': population_count,
            'rate': self.rate,
            'max_samples': self.max_samples,
            'seed': self.seed,
        }
