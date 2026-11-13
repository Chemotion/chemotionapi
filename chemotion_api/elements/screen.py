"""Screens: a set of wellplates, and the research plans that describe them, tested together.

Mirrors the ELN's own empty screen (``Screen.buildEmpty`` in the frontend) for new elements.
"""
from typing import cast

from chemotion_api.models import ScreenPropertiesModel
from chemotion_api.elements.abstract_element import AbstractElement
from chemotion_api.utils import quill_hedging

#: Writable scalar fields, sent on every save.
SCREEN_FIELDS = ('name', 'collaborator', 'requirements', 'conditions', 'result')


class Screen(AbstractElement):
    """A Chemotion screen.

    The linked wellplates and research plans are held as **id lists**,
    :attr:`wellplate_ids` and :attr:`research_plan_ids`, and those lists are what a save sends.
    The server *replaces* the links with whatever a save carries, so the lists always hold the
    current state; an empty list unlinks everything. :attr:`wellplates` and
    :attr:`research_plans` load the linked elements, one request each.

    Usage::

        >>> screen = collection.new_screen()
        >>> screen.properties['name'] = 'Kinase panel'
        >>> screen.wellplate_ids.append(wellplate.id)
        >>> screen.save()
    """

    _properties_model = ScreenPropertiesModel
    _rich_text_fields = ('description',)

    def _parse_properties(self) -> dict:
        data = cast(dict, self.json_data)
        self.wellplate_ids: list[int] = _ids(data.get('wellplates'))
        self.research_plan_ids: list[int] = _ids(data.get('research_plans'))
        return self._validated_properties({key: data.get(key) for key in SCREEN_FIELDS} | {
            'description': data.get('description'),
            'component_graph_data': data.get('component_graph_data'),
            'user_labels': data.get('user_labels') or [],
        })

    def _clean_properties_data(self, serialize_data: dict | None = None) -> dict:
        props = self.properties
        description = props.get('description')
        out = {key: props.get(key) for key in SCREEN_FIELDS} | {
            'description': quill_hedging(description, 'Description') if description is not None
            else {'ops': [{'insert': ''}]},
            'component_graph_data': props.get('component_graph_data') or {'nodes': [], 'edges': []},
            'user_labels': list(props.get('user_labels') or []),
            # Required by both create and update, and applied as a replacement.
            'wellplate_ids': list(self.wellplate_ids),
            'research_plan_ids': list(self.research_plan_ids),
        }
        return out | (serialize_data or {})

    @property
    def wellplates(self) -> list:
        """The linked wellplates, loaded from the server (one request each)."""
        from chemotion_api.elements.wellplate import Wellplate
        return [Wellplate(self._generic_segments, self._session, id=i, element_type='wellplate')
                for i in self.wellplate_ids]

    @property
    def research_plans(self) -> list:
        """The linked research plans, loaded from the server (one request each)."""
        from chemotion_api.elements.research_plan import ResearchPlan
        return [ResearchPlan(self._generic_segments, self._session, id=i, element_type='research_plan')
                for i in self.research_plan_ids]


def _ids(entries) -> list[int]:
    return [e['id'] for e in entries or [] if isinstance(e, dict) and isinstance(e.get('id'), int)]
