.. ChemotionAPI documentation master file, created by
   sphinx-quickstart on Mon Jun 12 12:14:22 2023.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to ChemotionAPI's documentation!
========================================

This is a python api for `Chemotion <https://chemotion.net/>`_. Chemotion is an Electronic Laboratory Notebook (ELN) developed at
the KIT. Chemotion is a web-based platform designed to help researchers manage and organize their experimental data in a secure and
efficient manner.

The ChemotionApi Python package is a wrapper for the RESTful API built on top of the Ruby on Rails
framework that allows users to interact with Chemotion ELN. The package provides a simple and intuitive
interface for creating, retrieving, updating, and deleting data stored in the ELN using Python. With
its RESTful architecture and comprehensive documentation, the ChemotionApi allows users to build custom applications and
workflows that leverage the ELN's capabilities and streamline their research processes.

.. important::
   **This release requires Chemotion ELN v4.** ELN 3.x and older are not supported: v4 rewrote
   collections and sharing, renumbered the share permission levels, and removed the
   ``/syncCollections`` API, so there is no meaningful overlap. Connecting to an older instance
   raises :class:`~chemotion_api.schema_manager.UnsupportedServerVersion` from
   :meth:`~chemotion_api.Instance.test_connection` — before any credentials are sent.

   **For an ELN 3.1.x server, use the** ``312.x`` **release line instead.** The package version
   tracks the server it targets: ``400.x.y`` ↔ ELN 4.0, ``312.x.y`` ↔ ELN 3.1.2,
   ``211.x.y`` ↔ ELN 2.1.1.

.. note::
   **Not every element type is equally supported.** Samples and reactions are first-class:
   they are read and written over the API and carry typed element data. Wellplates, research
   plans and LabIMotion generic elements are read and written over the API. Screens, cell lines,
   device descriptions and vessels are not supported by any part of this client.

.. toctree::
   :maxdepth: 2

   Examples
   Instance
   Collection
   Elements
   ResearchPlanDetails
   SampleDetails
   ReactionDetails
   WellplateDetails
   GenericElementsDetails
   Segments
   Attachments
   Analyses
   Search
   Admin

.. toctree::
   :maxdepth: 1
   :caption: Full API reference (all modules & internal helpers)

   api/modules


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
