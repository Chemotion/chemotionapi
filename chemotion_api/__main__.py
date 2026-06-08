"""Command-line entry point: the ``chemotion_api`` Click CLI for managing local Chemotion ELN instances via Docker Compose."""
import os.path

import click
import configparser

from chemotion_api.commands import InstanceManager


def deactivate_prompts(ctx, param, value):
    """Click callback for ``--quiet``: disable all interactive prompts on the command.

    :param ctx: The Click context
    :param param: The Click parameter that triggered the callback
    :param value: The flag value; when truthy, every prompting option is silenced
    :return: ``value`` unchanged
    """
    if value:
        for p in ctx.command.params:
            if isinstance(p, click.Option) and p.prompt is not None:
                p.prompt = None
    return value


def read_config(ctx, param, value):
    """Click callback for ``--config``: load option defaults from an INI config file.

    Values in the ``[INSTANCE]`` section override the default of any command option whose name
    matches a key in that section.

    :param ctx: The Click context
    :param param: The Click parameter that triggered the callback
    :param value: The path to the config file, or a non-string value to ignore
    :return: ``value`` unchanged
    """
    if isinstance(value, str):
        config = configparser.ConfigParser()
        config.read(value)
        i = config['INSTANCE']
        for p in ctx.command.params:
            for opt in p.opts:
                opt = str(opt).lstrip('-')
                if opt in i:
                    p.default = i[opt]
    return value


def add_options():
    """Build a decorator that adds the shared ``--quiet`` and ``--config`` options to a command.

    :return: A decorator that applies the common options to the function it decorates
    """
    cmd_options = [
        click.option('-q/--quiet', is_flag=True, default=False, is_eager=True, expose_value=False,
                     callback=deactivate_prompts, help='Supress user prompts'),
        click.option('--config', is_eager=True, expose_value=False, callback=read_config, help='Path to config file')
    ]

    def _add_options(func):
        for option in reversed(cmd_options):
            func = option(func)
        return func

    return _add_options


def add_db_options():
    """Build a decorator that adds the shared PostgreSQL connection options to a command.

    The options cover ``--pguser``, ``--port``, ``--host``, ``--pgpassword`` and ``--database``.

    :return: A decorator that applies the database options to the function it decorates
    """
    cmd_options = [
        click.option('--pguser', default='postgres', help="Postgresql User"),
        click.option('--port', default='5432', help="Postgresql server port"),
        click.option('--host', default='localhost', help="Postgresql server host"),
        click.option('--pgpassword', default='postgres', help="Postgresql password"),
        click.option('--database', default='chemotion', help="Postgresql database")
    ]

    def _add_options(func):
        for option in reversed(cmd_options):
            func = option(func)
        return func

    return _add_options


@click.group()
def cli():
    """Root command group for the ``chemotion_api`` CLI managing local Chemotion ELN instances."""
    pass


@cli.command(help="Fetch all available Version of Chemotion")
@add_options()
def available_versions():
    """Fetch and print all available Chemotion versions."""
    a = InstanceManager.get_versions()
    click.echo('\n'.join(a))


@cli.command(help="Check all running containers")
@click.option('--docker_compose_path', '-df', prompt='Your name',
              help='Path to docker compose directory', default='./docker-compose.yml')
@add_options()
def check(docker_compose_path):
    """Check the status of all running containers of the instance.

    :param docker_compose_path: Path to the Docker Compose file (relative to the working directory)
    """
    df = os.path.abspath(os.path.join(os.getcwd(), docker_compose_path))
    InstanceManager(df).check()


@cli.command(help="Same as docker compose up <services>")
@click.option('--docker_compose_path', '-df', prompt='Your name',
              help='Path to docker compose directory', default='./docker-compose.yml')
@add_options()
@click.argument('services', nargs=-1, type=click.UNPROCESSED)
def up(docker_compose_path, services):
    """Start the instance's services (equivalent to ``docker compose up <services>``).

    :param docker_compose_path: Path to the Docker Compose file (relative to the working directory)
    :param services: The services to start; if empty, all services are started
    """
    df = os.path.abspath(os.path.join(os.getcwd(), docker_compose_path))
    services_obj = {'eln': True, 'db': True, 'worker': True, 'ketchersvc': True, 'msconvert': True, 'spectra': True,
                    'converter': True}
    if len(services) != 0:
        for k, v in services_obj.items():
            services_obj[k] = k in services

    InstanceManager(df).up(**services_obj)
    click.echo('Docker-compose is up!')


@cli.command(help="Same as docker compose stop <services>")
@click.option('--docker_compose_path', '-df', prompt='Your name',
              help='Path to docker compose directory', default='./docker-compose.yml')
@add_options()
@click.argument('services', nargs=-1, type=click.UNPROCESSED)
def stop(docker_compose_path, services):
    """Stop the instance's services (equivalent to ``docker compose stop <services>``).

    :param docker_compose_path: Path to the Docker Compose file (relative to the working directory)
    :param services: The services to stop; if empty, all services are stopped
    """
    df = os.path.abspath(os.path.join(os.getcwd(), docker_compose_path))
    services_obj = {'eln': True, 'db': True, 'worker': True, 'ketchersvc': True, 'msconvert': True, 'spectra': True,
                    'converter': True}
    if len(services) != 0:
        for k, v in services_obj.items():
            services_obj[k] = k in services

    InstanceManager(df).stop(**services_obj)
    click.echo('Docker-compose is stoped!')


@cli.command(help="Same as docker compose down <services>")
@click.option('--docker_compose_path', '-df', prompt='Your name',
              help='Path to docker compose directory', default='./docker-compose.yml')
@add_options()
@click.argument('services', nargs=-1, type=click.UNPROCESSED)
def down(docker_compose_path, services):
    """Tear down the instance's services (equivalent to ``docker compose down <services>``).

    :param docker_compose_path: Path to the Docker Compose file (relative to the working directory)
    :param services: The services to bring down; if empty, all services are brought down
    """
    df = os.path.abspath(os.path.join(os.getcwd(), docker_compose_path))
    services_obj = {'eln': True, 'db': True, 'worker': True, 'ketchersvc': True, 'msconvert': True, 'spectra': True,
                    'converter': True}
    if len(services) != 0:
        for k, v in services_obj.items():
            services_obj[k] = k in services

    InstanceManager(df).down(**services_obj)
    click.echo('Docker-compose is down!')


@cli.command(help="Create a new docker-compose file with all necessary files and directories for a new chemotion instance.")
@click.option('--ignore_exist', is_flag=True,
              help='If set it will not raise an error in case the target folder is not empty.', default=False)
@click.option('--docker_compose_path', '-df', prompt='Your name',
              help='Path to docker compose directory', default='./docker-compose.yml')
@click.option('--version', '-v', prompt='Specify a version',
              help='Chemcommandotion version to be used', default='latest')
@click.option('--url', prompt='Public ELN url',
              help='Public URL on which the ELN can be reached ', default='http://localhost:<ELN_PORT>')
@click.option('--eln_port', '-p', prompt='Port on which the ELN can be reached',
              help='Port on which the ELN can be reached from the host', default=4000)
@click.option('--postgres_port', prompt='Port on which the Postgres DB can be reached',
              help='Port on which the PostgreSQL DB can be reached from the host', default=5432)
@click.option('--adminer_port', prompt='Port on which the Adminer can be reached',
              help='Port on which the Adminer can be reached from the host', default=8080)
@add_options()
def new(ignore_exist, docker_compose_path, version, url, eln_port, postgres_port, adminer_port):
    """Create a new Docker Compose file plus the files and directories for a new Chemotion instance.

    :param ignore_exist: If set, do not raise an error when the target folder is not empty
    :param docker_compose_path: Path to the Docker Compose file to create
    :param version: The Chemotion version to use
    :param url: The public URL on which the ELN can be reached
    :param eln_port: The host port on which the ELN can be reached
    :param postgres_port: The host port on which the PostgreSQL DB can be reached
    :param adminer_port: The host port on which Adminer can be reached
    :raises click.ClickException: If the target folder is not empty and ``ignore_exist`` is not set
    """
    if url == 'http://localhost:<ELN_PORT>':
        url = str(url).replace('<ELN_PORT>', str(eln_port))
    df = os.path.abspath(os.path.join(os.getcwd(), docker_compose_path))
    try:
        InstanceManager(df).new_instance(version=version, url=url, eln_port=eln_port, postgres_port=postgres_port, adminer_port=adminer_port)
    except ValueError as e:
        if not ignore_exist:
            raise click.ClickException(e.__str__())
        return
    click.echo('Docker-compose file has been created')


@cli.command(help="Change the port on which the ELN can be reached from the host.")
@click.option('--docker_compose_path', '-df', prompt='Your name',
              help='Path to docker compose directory', default='./docker-compose.yml')
@click.option('--eln_port', '-p', prompt='Port on which the ELN can be reached',
              help='Port on which the ELN can be reached from the host', default=4000)
@add_options()
def change_port(docker_compose_path, eln_port):
    """Change the host port on which the ELN can be reached (requires a restart to take effect).

    :param docker_compose_path: Path to the Docker Compose file (relative to the working directory)
    :param eln_port: The new host port for the ELN
    """
    df = os.path.abspath(os.path.join(os.getcwd(), docker_compose_path))
    InstanceManager(df).update_port(eln_port=eln_port)
    click.echo('Docker-compose file has been updated (To activate the change, the instance must be restarted)')


@cli.command(help="Change the port on which the ELN DB can be reached from the host.")
@click.option('--docker_compose_path', '-df', prompt='Your name',
              help='Path to docker compose directory', default='./docker-compose.yml')
@click.option('--postgres_port', prompt='Port on which the ELN can be reached',
              help='Port on which the Postgresql DB can be reached from the host', default=5432)
@add_options()
def change_postgres_port(docker_compose_path, postgres_port):
    """Change the host port on which the ELN's PostgreSQL DB can be reached (requires a restart).

    :param docker_compose_path: Path to the Docker Compose file (relative to the working directory)
    :param postgres_port: The new host port for the PostgreSQL DB
    """
    df = os.path.abspath(os.path.join(os.getcwd(), docker_compose_path))
    InstanceManager(df).update_db_port(postgresql_port=postgres_port)
    click.echo('Docker-compose file has been updated (To activate the change, the instance must be restarted)')


@cli.command(help='Updated the version of Chemotion instance')
@click.option('--docker_compose_path', '-df', prompt='Your name',
              help='Path to docker compose directory', default='./docker-compose.yml')
@click.option('--version', '-v', prompt='Specify a version',
              help='Chemotion version to be used', default='latest')
@add_options()
def update_version(docker_compose_path, version):
    """Update the Chemotion instance to a given version (brings the instance down first).

    :param docker_compose_path: Path to the Docker Compose file (relative to the working directory)
    :param version: The Chemotion version to update to
    """
    df = os.path.abspath(os.path.join(os.getcwd(), docker_compose_path))
    instance = InstanceManager(df)
    instance.down()
    instance.update(version=version)
    click.echo('Docker-compose file has been updated')


@cli.command(help="Make a dump of the Chemotion PostgreSQL")
@click.option('--docker_compose_path', '-df',
              help="The path to the Docker Compose directory is not required. "
                   "However, either the specified docker_compose_path or the current "
                   "working directory have to lead to a docker-compose.yml file, the "
                   "script automatically retrieves the PostgreSQL port specified "
                   "in the Docker Compose file, utilizing it as the default value "
                   "for the port argument.", default='./docker-compose.yml')
@click.option('--tar_file', '-f', prompt='Output tar dump file',
              help='Path to output tar dump file', required=False, default='<db_name>_<time_stamp>.tar')
@add_options()
@add_db_options()
def backup(docker_compose_path, tar_file, **kwargs):
    """Create a tar dump of the Chemotion PostgreSQL database.

    If a Docker Compose file is found, the DB service is started and its port is used automatically.

    :param docker_compose_path: Path to the Docker Compose file (optional)
    :param tar_file: Path to the output tar dump file; the placeholder default is treated as unset
    :param kwargs: PostgreSQL connection options (pguser, port, host, pgpassword, database)
    """
    if tar_file == '<db_name>_<time_stamp>.tar':
        tar_file = None
    im = InstanceManager(docker_compose_path)
    if im.check_file():
        im.up(db=True)
        kwargs['port'] = im.db_port
    im.backup(file_path=tar_file, **kwargs)


@cli.command(help="Restore a ProstgreSQL dump. Make sure it is a valid dump in the tar format.")
@click.option('--docker_compose_path', '-df',
              help="The path to the Docker Compose directory is not required. "
                   "However, either the specified docker_compose_path or the current "
                   "working directory have to lead to a docker-compose.yml file, the "
                   "script automatically retrieves the PostgreSQL port specified "
                   "in the Docker Compose file, utilizing it as the default value "
                   "for the port argument.", default='./docker-compose.yml')
@click.option('--tar_file', '-f', prompt='Your tar dump file',
              help='Path to tar dump file')
@add_options()
@add_db_options()
def restore(docker_compose_path, tar_file, **kwargs):
    """Restore a PostgreSQL dump from a valid tar-format dump file.

    If a Docker Compose file is found, the DB service is started and its port is used automatically.

    :param docker_compose_path: Path to the Docker Compose file (optional)
    :param tar_file: Path to the tar dump file to restore from
    :param kwargs: PostgreSQL connection options (pguser, port, host, pgpassword, database)
    :raises click.ClickException: If the restore process fails
    """
    im = InstanceManager(docker_compose_path)
    if im.check_file():
        im.up(db=True)
        kwargs['port'] = im.db_port
    try:
        im.restore(tar_file, **kwargs)
    except ChildProcessError as e:
        raise click.ClickException(e.__str__())


@cli.command(help="Insert a dataset.")
@click.option('--docker_compose_path', '-df',
              help="The path to the Docker Compose directory is not required. "
                   "However, either the specified docker_compose_path or the current "
                   "working directory have to lead to a docker-compose.yml file, the "
                   "script automatically retrieves the PostgreSQL port specified "
                   "in the Docker Compose file, utilizing it as the default value "
                   "for the port argument.", default='./docker-compose.yml')
@click.option('--ols_term_id', '-ols',  prompt='OLS term id',
              help='OLS (OntoLogy Search) term ID CHMO:XXXX')
@add_options()
@add_db_options()
def insert_dataset(docker_compose_path, ols_term_id, **kwargs):
    """Insert a dataset identified by an OLS term id into the Chemotion database.

    If a Docker Compose file is found, the DB service is started and its port is used automatically.

    :param docker_compose_path: Path to the Docker Compose file (optional)
    :param ols_term_id: The OLS (Ontology Search) term id, e.g. ``CHMO:XXXX``
    :param kwargs: PostgreSQL connection options (pguser, port, host, pgpassword, database)
    :raises click.ClickException: If inserting the dataset fails
    """
    im = InstanceManager(docker_compose_path)

    if im.check_file():
        im.up(db=True)
        kwargs['port'] = im.db_port
    try:
        im.insert_dataset(ols_term_id, **kwargs)
    except ChildProcessError as e:
        raise click.ClickException(e.__str__())


if __name__ == '__main__':
    cli()
