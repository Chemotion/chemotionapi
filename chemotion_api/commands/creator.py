import os

from jinja2 import Environment, PackageLoader, select_autoescape


def walk_productive_template(url, eln_port, postgres_port, adminer_port, msconvert, spectra, eln, ketchersvc, converter, **kwargs):
    main_root_dir = os.path.join(os.path.dirname(__file__), 'templates/productive')
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
