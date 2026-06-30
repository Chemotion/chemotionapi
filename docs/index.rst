.. ChemotionAPI documentation master file, created by
   sphinx-quickstart on Mon Jun 12 12:14:22 2023.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to ChemotionAPI's documentation!
========================================

This is a python api for [Chemotion](https://chemotion.net/). Chemotion is a Electronic Laboratory Notebook (ELN) it is developed at
the KIT. Chemotion is a web-based platform designed to help researchers manage and organize their experimental data in a secure and
efficient manner.

The ChemotionApi Python package is a wrapper for the RESTful API built on top of the Ruby on Rails
framework that allows users to interact with Chemotion ELN. The package provides a simple and intuitive
interface for creating, retrieving, updating, and deleting data stored in the ELN using Python. With
its RESTful architecture and comprehensive documentation, the ChemotionApi allows users to build custom applications and
workflows that leverage the ELN's capabilities and streamline their research processes.

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
   Attachments
   Analyses
   FairExport
   OfflineIngestion
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
