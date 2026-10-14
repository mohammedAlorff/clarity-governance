"""Privacy sampling contracts; the database boundary never supplies field values."""

import json
import random
from dataclasses import FrozenInstanceError

import pytest

from governance.sampling import SamplingPolicy, length_bucket
from governance.source import DemoSource, MySQLSource


@pytest.fixture(autouse=True)
def clean_sampling_environment(monkeypatch):
    for name in ('PRIVACY_SAMPLE_RATE', 'PRIVACY_MAX_SAMPLES', 'PRIVACY_SAMPLE_SEED'):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize(
    'population,limit,expected',
    [
        (0, 10, 0),
        (1, 10, 1),
        (8, 8, 1),
        (20, 10, 1),
        (21, 10, 2),
        (100, 100, 5),
        (200, 100, 10),
        (1000, 3, 3),
    ],
)
def test_demo_applies_rate_requested_limit_and_absolute_cap(population, limit, expected):
    source = DemoSource()
    source.rows['customers'] = [{'email': 'CANARY@example.invalid'} for _ in range(population)]
    result = source.sample_column('customers', 'email', limit)
    assert result['sample_count'] == expected
    assert result['sampling'] == {
        'strategy': 'seeded_bounded_pool',
        'candidate_count': min(population, 100),
        'returned_count': expected,
        'population_count': population,
        'rate': 0.05,
        'max_samples': 10,
        'seed': 42,
    }
    assert result['redacted'] is True
    assert 'CANARY' not in json.dumps(result)


def test_demo_samples_only_first_hundred_candidates():
    source = DemoSource()
    source.rows['customers'] = [{'email': 123} for _ in range(100)] + [
        {'email': 'outside'} for _ in range(900)
    ]
    result = source.sample_column('customers', 'email', 100)
    assert result['samples'] == [{'type': 'number'}] * 10
    assert result['sampling']['candidate_count'] == 100


def test_selection_is_repeatable_nonprefix_and_does_not_change_global_rng():
    source = DemoSource()
    source.rows['customers'] = [{'email': None} for _ in range(10)] + [
        {'email': 'secret'} for _ in range(190)
    ]
    before = random.getstate()
    first = source.sample_column('customers', 'email', 5)
    second = source.sample_column('customers', 'email', 5)
    assert random.getstate() == before
    assert first == second
    assert any(shape['type'] == 'string' for shape in first['samples'])
    assert 'secret' not in json.dumps(first)


@pytest.mark.parametrize(
    'length,expected',
    [
        (0, '0'),
        (1, '1-4'),
        (4, '1-4'),
        (5, '5-8'),
        (8, '5-8'),
        (9, '9-16'),
        (17, '17-32'),
        (33, '33-64'),
        (65, '65-128'),
        (129, '129-256'),
        (257, '257-512'),
        (513, '513-1024'),
        (1025, '1025-4096'),
        (4096, '1025-4096'),
        (4097, '4097+'),
    ],
)
def test_string_descriptors_generalize_exact_lengths(length, expected):
    source = DemoSource()
    source.rows['customers'] = [{'email': 'x' * length}]
    result = source.sample_column('customers', 'email')
    assert result['samples'] == [{'type': 'string', 'length_bucket': expected}]


@pytest.mark.parametrize(
    'name,value',
    [
        ('PRIVACY_SAMPLE_RATE', '0'),
        ('PRIVACY_SAMPLE_RATE', '0.11'),
        ('PRIVACY_SAMPLE_RATE', 'nan'),
        ('PRIVACY_SAMPLE_RATE', 'inf'),
        ('PRIVACY_SAMPLE_RATE', ''),
        ('PRIVACY_MAX_SAMPLES', '0'),
        ('PRIVACY_MAX_SAMPLES', '11'),
        ('PRIVACY_MAX_SAMPLES', '1.5'),
        ('PRIVACY_SAMPLE_SEED', '-1'),
        ('PRIVACY_SAMPLE_SEED', '2147483648'),
        ('PRIVACY_SAMPLE_SEED', 'secret'),
    ],
)
def test_invalid_environment_fails_closed(name, value, monkeypatch):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        DemoSource().sample_column('customers', 'email')


def test_environment_can_reduce_sampling_and_change_seed(monkeypatch):
    monkeypatch.setenv('PRIVACY_SAMPLE_RATE', '0.02')
    monkeypatch.setenv('PRIVACY_MAX_SAMPLES', '3')
    monkeypatch.setenv('PRIVACY_SAMPLE_SEED', '19')
    source = DemoSource()
    source.rows['customers'] = [{'email': None}] * 1000
    result = source.sample_column('customers', 'email', 100)
    assert result['sample_count'] == 3
    assert result['sampling']['rate'] == 0.02
    assert result['sampling']['max_samples'] == 3
    assert result['sampling']['seed'] == 19


class DescriptorCursor:
    def __init__(self, connection):
        self.connection = connection
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def execute(self, sql, params):
        self.connection.queries.append((sql, params))
        if sql.startswith('SHOW GRANTS'):
            self.rows = [{'grant': 'GRANT SELECT ON `shop`.* TO `reader`@`localhost`'}]
        elif 'INFORMATION_SCHEMA.COLUMNS' in sql:
            self.rows = self.connection.columns
        elif 'COUNT(*) AS count' in sql:
            self.rows = [{'count': self.connection.population}]
        elif 'AS is_null' in sql:
            self.rows = self.connection.descriptors

    def fetchmany(self, limit):
        return self.rows[:limit]


class DescriptorConnection:
    def __init__(self, population=1000, descriptors=None):
        self.population = population
        self.descriptors = (
            descriptors if descriptors is not None else [{'is_null': False, 'length': 27}] * 100
        )
        self.queries = []
        self.closed = False
        self.columns = [
            {
                'TABLE_NAME': 'customers',
                'COLUMN_NAME': 'id',
                'DATA_TYPE': 'int',
                'IS_NULLABLE': 'NO',
                'COLUMN_KEY': 'PRI',
            },
            {
                'TABLE_NAME': 'customers',
                'COLUMN_NAME': 'email',
                'DATA_TYPE': 'varchar',
                'IS_NULLABLE': 'YES',
                'COLUMN_KEY': '',
            },
            {
                'TABLE_NAME': 'customers',
                'COLUMN_NAME': 'tenant',
                'DATA_TYPE': 'int',
                'IS_NULLABLE': 'NO',
                'COLUMN_KEY': 'PRI',
            },
        ]

    def cursor(self):
        return DescriptorCursor(self)

    def close(self):
        self.closed = True


def test_mysql_query_fetches_only_bounded_descriptors_and_orders_by_all_primary_keys():
    connection = DescriptorConnection()
    source = MySQLSource(connection, 'shop')
    result = source.sample_column('customers', 'email', 100)
    sql, params = connection.queries[-1]
    projection = sql.split(' FROM ')[0]
    assert (
        '(`email` IS NULL) AS is_null, CHAR_LENGTH(CAST(`email` AS CHAR)) AS length' in projection
    )
    assert '`id`' not in projection and '`tenant`' not in projection
    assert 'ORDER BY `id`,`tenant` LIMIT 100' in sql
    assert params == ()
    assert result['sample_count'] == 10
    assert result['samples'] == [{'type': 'string', 'length_bucket': '17-32'}] * 10
    assert result['sampling']['candidate_count'] == 100
    assert result == source.sample_column('customers', 'email', 100)


@pytest.mark.parametrize(
    'population,descriptors,expected',
    [
        (0, [], 0),
        (1, [{'is_null': True, 'length': None}], 1),
        (1000, [{'is_null': False, 'length': 0}], 1),
    ],
)
def test_mysql_sample_count_never_exceeds_available_candidates(population, descriptors, expected):
    source = MySQLSource(DescriptorConnection(population, descriptors), 'shop')
    result = source.sample_column('customers', 'email', 100)
    assert result['sample_count'] == expected
    assert result['sampling']['candidate_count'] == len(descriptors)


def test_mysql_without_primary_key_still_bounds_descriptor_query():
    connection = DescriptorConnection()
    for column in connection.columns:
        column['COLUMN_KEY'] = ''
    result = MySQLSource(connection, 'shop').sample_column('customers', 'email', 100)
    sql = connection.queries[-1][0]
    assert 'ORDER BY' not in sql
    assert sql.endswith('LIMIT 100')
    assert result['sample_count'] == 10


def test_mysql_invalid_policy_fails_before_issuing_sample_query(monkeypatch):
    connection = DescriptorConnection()
    source = MySQLSource(connection, 'shop')
    before = len(connection.queries)
    monkeypatch.setenv('PRIVACY_SAMPLE_RATE', '0.5')
    with pytest.raises(ValueError):
        source.sample_column('customers', 'email')
    assert len(connection.queries) == before


@pytest.mark.parametrize(
    'settings',
    [
        {'rate': True},
        {'rate': '0.05'},
        {'rate': 10**1000},
        {'max_samples': True},
        {'max_samples': 1.5},
        {'max_samples': 11},
        {'seed': False},
        {'seed': 0.5},
        {'seed': -1},
        {'seed': 2147483648},
        {'candidate_pool': True},
        {'candidate_pool': 0},
        {'candidate_pool': 101},
    ],
)
def test_direct_policy_cannot_bypass_privacy_validation(settings):
    with pytest.raises(ValueError):
        SamplingPolicy(**settings)


def test_frozen_policy_prevents_mutating_validated_limits():
    policy = SamplingPolicy()
    with pytest.raises(FrozenInstanceError):
        policy.max_samples = 100


def test_selection_does_not_read_candidates_past_the_bounded_pool():
    def candidates():
        for _ in range(100):
            yield {'type': 'null'}
        raise AssertionError('Candidate consumption exceeded the privacy limit')

    selected, audit = SamplingPolicy().select(candidates(), 10**1000, 100)
    assert len(selected) == 10
    assert audit['candidate_count'] == 100
    assert audit['population_count'] == 10**1000


def test_rate_budget_uses_decimal_boundaries_without_float_rounding():
    selected, _ = SamplingPolicy(rate=0.07).select([{'type': 'null'}] * 100, 100, 100)
    assert len(selected) == 7


def test_different_seed_changes_selection_and_keeps_input_order_untouched():
    candidates = [{'type': 'string', 'length_bucket': str(i)} for i in range(100)]
    before = list(candidates)
    first, _ = SamplingPolicy(seed=1).select(candidates, 1000, 10)
    second, _ = SamplingPolicy(seed=2).select(candidates, 1000, 10)
    assert first != second
    assert candidates == before


@pytest.mark.parametrize(
    'population,limit',
    [(-1, 10), (True, 10), (1.0, 10), (10, 0), (10, 101), (10, True), (10, '10')],
)
def test_selection_rejects_invalid_population_and_request(population, limit):
    with pytest.raises(ValueError):
        SamplingPolicy().select([], population, limit)


@pytest.mark.parametrize('length', [-1, True, 1.2, 'secret', None])
def test_length_bucketing_rejects_malformed_descriptors(length):
    with pytest.raises(ValueError):
        length_bucket(length)
