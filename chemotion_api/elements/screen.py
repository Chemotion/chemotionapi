"""Screen element: a set of wellplates (and research plans) screened together."""
from __future__ import annotations

from typing import cast

from chemotion_api.connection import request_error
from chemotion_api.elements.abstract_element import AbstractElement
from chemotion_api.elements.registry import register_element_type
from chemotion_api.elements.research_plan import ResearchPlan
from chemotion_api.elements.wellplate import Wellplate

#: The plain-text fields of a screen, as ``screen_api.rb`` declares them.
TEXT_FIELDS = ('name', 'collaborator', 'requirements', 'conditions', 'result')


@register_element_type('screen', url='/api/v1/screens')
class Screen(AbstractElement):
    """
    A screen groups wellplates — and research plans describing the experiment — that are screened
    together. It extends :class:`chemotion_api.elements.abstract_element.AbstractElement`.

    Its properties are ``name``, ``collaborator``, ``requirements``, ``conditions`` and ``result``
    (plain strings), ``description`` (a Quill delta like a wellplate's), and the linked
    ``wellplates`` and ``research_plans``. The links are saved by id, so a wellplate or research plan
    has to be saved before it can be added.

    Usage::

    >>> screen = collection.new_screen()
    >>> screen.properties['name'] = 'Kinase panel'
    >>> plate = collection.new_wellplate()
    >>> plate.save()
    >>> screen.add_wellplate(plate)
    >>> screen.save()
    >>> plan = screen.new_research_plan(collection)  # created and linked by the server
    """

    def _parse_properties(self) -> dict:
        data = cast(dict, self.json_data)
        props: dict = {key: data.get(key) for key in TEXT_FIELDS}
        props['description'] = data.get('description')
        props['wellplates'] = [Wellplate(self._generic_segments, self._session, json_data=wp)
                               for wp in data.get('wellplates') or []]
        props['research_plans'] = [ResearchPlan(self._generic_segments, self._session, json_data=rp)
                                   for rp in data.get('research_plans') or []]
        return props

    def _clean_properties_data(self, serialize_data: dict | None = None) -> dict:
        # The nested wellplate/research-plan records are not sent back: the server takes the links
        # as id lists, and every PUT requires both (an empty list unlinks everything).
        out = {k: v for k, v in cast(dict, self.json_data).items() if k not in ('wellplates', 'research_plans')}
        for key in TEXT_FIELDS:
            out[key] = self.properties.get(key)
        out['description'] = self.properties.get('description')
        out['wellplate_ids'] = [self._saved_id(wp, 'wellplate') for wp in self.wellplates]
        out['research_plan_ids'] = [self._saved_id(rp, 'research plan') for rp in self.research_plans]
        return out

    @staticmethod
    def _saved_id(element: AbstractElement, kind: str) -> int:
        if element.id is None:
            raise ValueError(f'Save the {kind} before linking it to a screen.')
        return element.id

    @property
    def wellplates(self) -> list[Wellplate]:
        """The wellplates of this screen (``properties['wellplates']``)."""
        return self.properties['wellplates']

    @property
    def research_plans(self) -> list[ResearchPlan]:
        """The research plans linked to this screen (``properties['research_plans']``)."""
        return self.properties['research_plans']

    def add_wellplate(self, wellplate: Wellplate) -> Screen:
        """Link a saved wellplate to this screen. Sent on :meth:`save`; adding it twice is a no-op."""
        self._add_link(self.wellplates, wellplate, 'wellplate')
        return self

    def remove_wellplate(self, wellplate: Wellplate) -> Screen:
        """Unlink a wellplate. The wellplate itself is not deleted. Sent on :meth:`save`."""
        self.wellplates[:] = [wp for wp in self.wellplates if wp.id != wellplate.id]
        return self

    def add_research_plan(self, research_plan: ResearchPlan) -> Screen:
        """Link a saved research plan to this screen. Sent on :meth:`save`."""
        self._add_link(self.research_plans, research_plan, 'research plan')
        return self

    def remove_research_plan(self, research_plan: ResearchPlan) -> Screen:
        """Unlink a research plan. The plan itself is not deleted. Sent on :meth:`save`."""
        self.research_plans[:] = [rp for rp in self.research_plans if rp.id != research_plan.id]
        return self

    def _add_link(self, links: list, element: AbstractElement, kind: str) -> None:
        self._saved_id(element, kind)
        if all(link.id != element.id for link in links):
            links.append(element)

    def new_research_plan(self, collection) -> ResearchPlan:
        """Have the server create a research plan for this screen and link it, right away.

        ``POST /api/v1/screens/:id/add_research_plan``, the UI's "add research plan" button. The
        plan is named ``New Research Plan <n> for <screen name>`` and placed in ``collection``.
        Unsaved changes to this screen are kept; the screen's research plans are refreshed from the
        server's answer.

        :param collection: one of your own collections to put the new plan in.
        :return: the new research plan.
        :raises ValueError: if the screen has not been saved.
        """
        if self.id is None:
            raise ValueError('Save the screen before adding a research plan to it.')
        res = self._session.post(f'{self.get_url(self.element_type)}/{self.id}/add_research_plan',
                                 data={'collection_id': collection.id})
        if res.status_code not in (200, 201):
            raise request_error(res, f'adding a research plan to screen {self.id}')
        server_plans = (res.json().get('screen') or {}).get('research_plans') or []
        known = {rp.id for rp in self.research_plans}
        new_plans = [ResearchPlan(self._generic_segments, self._session, json_data=rp)
                     for rp in server_plans if rp.get('id') not in known]
        self.research_plans.extend(new_plans)
        cast(dict, self.json_data)['research_plans'] = server_plans
        if not new_plans:
            raise ConnectionError(f'Screen {self.id}: the server reported no new research plan.')
        return new_plans[-1]
