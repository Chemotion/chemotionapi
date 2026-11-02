# Minimal makefile for Sphinx documentation
#

# You can set these variables from the command line, and also
# from the environment for the first two.
SPHINXOPTS    ?=
SPHINXBUILD   ?= sphinx-build
SPHINXAPIDOC  ?= sphinx-apidoc
SOURCEDIR     = .
BUILDDIR      = _build
# Package to auto-document and where the generated per-module pages go.
PACKAGE       = ../chemotion_api
APIDIR        = api
# Full reference: include internal/private + undocumented helpers; no-index keeps these pages from
# clashing with the curated topic guides (which stay the canonical index entries).
APIDOC_OPTIONS = members,undoc-members,private-members,show-inheritance,no-index

# Put it first so that "make" without argument is like "make help".
help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

# Regenerate the full API reference (every module + internal helper) under $(APIDIR)/.
apidoc:
	@SPHINX_APIDOC_OPTIONS="$(APIDOC_OPTIONS)" $(SPHINXAPIDOC) -f -e -o "$(APIDIR)" "$(PACKAGE)"

# Build HTML, regenerating the API reference first.
html: apidoc
	@$(SPHINXBUILD) -M html "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

# Remove the build output and the generated API pages.
clean:
	@$(SPHINXBUILD) -M clean "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)
	@rm -rf "$(APIDIR)"

.PHONY: help apidoc html clean Makefile

# Catch-all for other Sphinx builders (latexpdf, epub, ...); regenerate the API reference first.
%: Makefile apidoc
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)
