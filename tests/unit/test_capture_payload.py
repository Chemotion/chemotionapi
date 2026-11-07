"""The payload capture tool's offline helpers (M0.2): selecting a sub-tree and scrubbing it."""
import importlib.util
import os

import pytest

_PATH = os.path.join(os.path.dirname(__file__), os.pardir, 'tools', 'capture_payload.py')
_spec = importlib.util.spec_from_file_location('capture_payload', _PATH)
capture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(capture)

RESPONSE = {'klass': [{'id': 1, 'element_klass': {'id': 2, 'label': 'x'}}, {'id': 3}]}


@pytest.mark.parametrize('path, expected', [
    (None, RESPONSE),
    ('klass[1]', {'id': 3}),
    ('klass[0].element_klass.label', 'x'),
])
def test_select_walks_keys_and_indexes(path, expected):
    assert capture.select(RESPONSE, path) == expected


@pytest.mark.parametrize('path', ['klass[5]', 'nope', 'klass[0].id.deeper'])
def test_select_names_the_missing_step(path):
    with pytest.raises(SystemExit, match='--select'):
        capture.select(RESPONSE, path)


def test_scrub_pins_every_timestamp_format_the_server_uses():
    data = {'a': '2026-11-07T09:52:26+0000', 'b': ['2026-11-07T09:52:26.123Z', '2026-11-07T09:52:26+01:00'],
            'c': 'not 2026-11-07T09:52:26+0000', 'd': 5}
    assert capture.scrub(data, timestamps=True, drop=set()) == {
        'a': capture.FIXED_TIMESTAMP, 'b': [capture.FIXED_TIMESTAMP, capture.FIXED_TIMESTAMP],
        'c': 'not 2026-11-07T09:52:26+0000', 'd': 5}


def test_scrub_leaves_timestamps_alone_unless_asked():
    assert capture.scrub({'a': '2026-11-07T09:52:26+0000'}, timestamps=False, drop=set()) == \
        {'a': '2026-11-07T09:52:26+0000'}


def test_scrub_drops_keys_at_every_depth():
    data = {'keep': 1, 'secret': 2, 'nested': [{'secret': 3, 'keep': 4}]}
    assert capture.scrub(data, timestamps=False, drop={'secret'}) == {'keep': 1, 'nested': [{'keep': 4}]}


def test_a_bare_output_name_goes_into_the_unit_test_data_dir(tmp_path):
    assert capture.output_path('x.json') == os.path.join(capture.DEFAULT_OUT_DIR, 'x.json')
    assert capture.output_path(str(tmp_path / 'x.json')) == str(tmp_path / 'x.json')
