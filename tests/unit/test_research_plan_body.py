"""Offline unit tests for the research-plan body building blocks (Table, RichText).

Both are plain dict subclasses describing body entries; no server is involved until save().
"""
import pytest

from chemotion_api.elements.research_plan import BodyElements, RichText, Table


def _table() -> Table:
    return Table(id='t1', value={})


# --- Table -------------------------------------------------------------------------------------

def test_table_shape_and_id():
    t = Table(id='t1', value={}, start_collapsed=True)
    assert t.id == 't1'
    assert t['type'] == BodyElements.table.value
    assert t['startCollapsed'] is True
    assert t['value'] == {'columns': [], 'rows': []}


def test_add_columns_returns_ids_and_backfills_rows():
    t = _table()
    t.add_row()                                  # a pre-existing (empty) row
    name_id, age_id = t.add_columns('Name', 'Age')
    assert name_id != age_id
    assert t.column_id_by_label('Name') == name_id
    assert list(t.column_ids_by_labels('Age', 'Name')) == [age_id, name_id]
    # the pre-existing row gained the new columns
    assert name_id in t['value']['rows'][0]


def test_add_row_positional_placed_and_padded():
    t = _table()
    name_id, age_id, dev_id = t.add_columns('Name', 'Age', 'Is Developer')
    t.add_row('Mr. X', False, **{age_id: 30}).add_row('Mr. Y')
    assert t['value']['rows'][0] == {name_id: 'Mr. X', age_id: 30, dev_id: False}
    # missing entries are padded with ''
    assert t['value']['rows'][1] == {name_id: 'Mr. Y', age_id: '', dev_id: ''}
    assert len(t) == 2


def test_set_entry_and_get_column():
    t = _table()
    name_id, age_id = t.add_columns('Name', 'Age')
    t.add_row('A', 1).add_row('B', 2)
    t.set_entry(1, age_id, 40)
    assert t.get_column(age_id) == [1, 40]
    assert t.get_column(name_id) == ['A', 'B']


def test_column_id_by_unknown_label_raises():
    t = _table()
    t.add_columns('Name')
    with pytest.raises(KeyError, match='No Such Column'):
        t.column_id_by_label('No Such Column')


# --- RichText ----------------------------------------------------------------------------------

def test_richtext_shape_and_plain_text():
    rt = RichText(id='r1')
    assert rt.id == 'r1'
    assert rt['type'] == BodyElements.richtext.value
    rt.add_text('hello')
    assert rt.value == [{'insert': 'hello'}]


def test_richtext_formatting_attributes():
    rt = RichText(id='r1')
    rt.add_text('title', header=RichText.HeaderType.H2)
    rt.add_text('important', bold=True, underline=True, italic=True)
    rt.add_text('item', list='bullet')
    assert rt.value[0]['attributes'] == {'header': RichText.HeaderType.H2.value}
    assert rt.value[1]['attributes'] == {'bold': True, 'underline': True, 'italic': True}
    assert rt.value[2]['attributes'] == {'list': 'bullet'}
    # chaining returns self
    assert rt.add_text('x') is rt
