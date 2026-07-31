"""Render the bundled ``templates/productive`` Jinja2 tree for a new instance.

Used by :meth:`chemotion_api.commands.InstanceManager.new_instance` to scaffold a fresh
Docker Compose deployment.
"""
import os

from jinja2 import Environment, PackageLoader, select_autoescape

from chemotion_api.utils import resource_path


def walk_productive_template(url, eln_port, postgres_port, adminer_port, msconvert, spectra, eln, ketchersvc, converter, **kwargs):
    """Walk the productive template tree, yielding rendered files and directory markers.

    Each template is rendered with the given deployment context (URL, ports, and per-service
    image references).

    :param url: external base URL of the instance.
    :param eln_port: host port for the ELN web service.
    :param postgres_port: host port for PostgreSQL.
    :param adminer_port: host port for Adminer.
    :param msconvert: image reference for the msconvert service.
    :param spectra: image reference for the spectra service.
    :param eln: image reference for the ELN service.
    :param ketchersvc: image reference for the Ketcher service.
    :param converter: image reference for the converter service.
    :param kwargs: additional template context / image references.
    :return: an iterator of ``(is_file, relative_path, content)`` tuples; ``content`` is the
        rendered text for files and ``None`` for directories.
    """
    main_root_dir = os.path.join(resource_path(__file__), 'templates/productive')
    for root, dir, files in os.walk(main_root_dir):

        env = Environment(
            loader=PackageLoader("chemotion_api", package_path=root),

            autoescape=select_autoescape()
        )

        context = dict(url=url, eln_port=eln_port, postgres_port=postgres_port, adminer_port=adminer_port,
                       msconvert=msconvert, spectra=spectra, eln=eln, ketchersvc=ketchersvc, converter=converter, **kwargs)

        for f in files:
            rel_root = os.path.relpath(os.path.join(root, f), main_root_dir)
            t = env.get_template(f)
            yield (True, rel_root, t.render(**context))
        for d in dir:
            rel_root = os.path.relpath(os.path.join(root, d), main_root_dir)
            yield (False, rel_root, None)
