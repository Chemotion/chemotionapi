from chemotion_api.elements.reaction import Variations


def _variations(rows):
    variations = Variations(None, [], [], [], [], vessel_size=lambda: {})
    variations.populate(rows)
    return variations


def test_all_variations_get_the_same_metadata_and_properties():
    # A row created in the ELN only has the keys of the columns selected at the time
    browser_row = {'id': 1, 'metadata': {'notes': 'Test'},
                   'properties': {'duration': {'value': 3, 'unit': 'Second(s)'}}}
    api_row = Variations.empty_variation(2)
    api_row['metadata']['notes'] = 'API'

    first, second = _variations([browser_row, api_row]).clean()

    assert first['metadata'] == {'notes': 'Test', 'analyses': []}
    assert first['properties'] == {'duration': {'value': 3, 'unit': 'Second(s)'},
                                   'temperature': {'value': 0, 'unit': '°C'}}
    assert second['metadata'] == {'notes': 'API', 'analyses': []}


def test_missing_metadata_and_properties():
    row, = _variations([{'id': 1}]).clean()
    assert row['metadata'] == {'notes': ''}
    assert row['properties'] == {}
