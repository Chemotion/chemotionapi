# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
#
import os
import sys
sys.path.insert(0, os.path.abspath('..'))

# Options applied to every automodule directive the auto-generated API reference emits. Set before
# sphinx.ext.apidoc is imported (it reads this env var at import time). ``no-index`` keeps the full
# reference from clashing with the curated topic guides (which stay the canonical index entries).
os.environ.setdefault(
    'SPHINX_APIDOC_OPTIONS',
    'members,undoc-members,private-members,show-inheritance,no-index',
)


# -- Project information -----------------------------------------------------

project = 'Chemotion API (Pydantic & chem-dcat-ap)'
copyright = '2023-2026, Martin Starman <martin.starman@kit.edu> and contributors'
author = 'Martin Starman and contributors'
release = '312.0.0'


# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = ['sphinx.ext.autodoc', 'sphinx.ext.napoleon', 'sphinx.ext.coverage', 'enum_tools.autoenum', 'sphinx_rtd_theme']
# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# Nicer autodoc output: document members in source order, and merge the class docstring with the
# __init__ docstring.
autodoc_member_order = 'bysource'
autoclass_content = 'both'
# Let the docs build without the heavy scientific stack installed (these are only needed at runtime
# for the actual .eln export; autodoc just needs to import the modules to read signatures/docstrings).
autodoc_mock_imports = ['rdflib', 'linkml_runtime', 'chem_dcat_ap', 'dcat_ap_plus', 'pyshacl']

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']


# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
html_theme = 'sphinx_rtd_theme'

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ['_static']


# -- Auto-generate the full API reference on every build ---------------------
# The Makefile's `apidoc` target regenerates docs/api/ before building, but bare `sphinx-build`
# and Read the Docs invoke Sphinx directly (no Makefile). This hook runs sphinx-apidoc on
# `builder-inited` so the full reference (every module + internal helper) is always present.
def _run_apidoc(_app):
    from sphinx.ext import apidoc  # reads SPHINX_APIDOC_OPTIONS (set at module top) on import
    docs_dir = os.path.dirname(os.path.abspath(__file__))
    package = os.path.join(docs_dir, '..', 'chemotion_api')
    out_dir = os.path.join(docs_dir, 'api')
    apidoc.main(['-f', '-e', '-o', out_dir, package])


def setup(app):
    app.connect('builder-inited', _run_apidoc)