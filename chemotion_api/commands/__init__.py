"""Manage local Chemotion ELN instances via Docker Compose.

:class:`InstanceManager` wraps a ``docker-compose.yml`` file: it can scaffold a new productive
instance from bundled templates, pull/select image versions from Docker Hub, start/stop/tear down
selected services, read/update host ports, back up and restore the PostgreSQL database, and seed
dataset ontology classes from OLS. Most operations shell out to ``docker compose``, ``pg_dump`` /
``pg_restore`` and friends.
"""
import os
import subprocess
from datetime import datetime
from .creator import walk_productive_template

import click
import requests

from .updater import update_images, update_eln_port, update_db_port, get_eln_port, get_db_port


class InstanceManager:
    """Operate on a single Chemotion instance described by a ``docker-compose.yml`` file.

    :param df: either a directory containing a ``docker-compose.yml`` or a path to a compose
        file. Defaults to the current working directory.
    """

    def __init__(self, df=None):
        if df is None:
            df = os.getcwd()
        if os.path.isdir(df):
            self._df_name = 'docker-compose.yml'
            self._df_dir = df
        else:
            self._df_dir = os.path.dirname(df)
            self._df_name = os.path.basename(df)

    @property
    def eln_port(self):
        """The host port mapped to the ELN service, read from the compose file."""
        df = self._check_file()
        return get_eln_port(df)

    @property
    def db_port(self):
        """The host port mapped to the database service, read from the compose file."""
        df = self._check_file()
        return get_db_port(df)

    def update(self, version=None):
        """Update the service images in the compose file to the given (or latest) version.

        :param version: image version tag; defaults to the latest available version.
        """
        df = self._check_file()
        images = self.get_image_of_versions(version)
        update_images(df, **images)

    def update_port(self, eln_port):
        """Set the host port mapped to the ELN service in the compose file.

        :param eln_port: new host port for the ELN web service.
        """
        df = self._check_file()
        update_eln_port(df, eln_port)

    def update_db_port(self, postgresql_port):
        """Set the host port mapped to the database service in the compose file.

        :param postgresql_port: new host port for the PostgreSQL service.
        """
        df = self._check_file()
        update_db_port(df, postgresql_port)

    def check(self):
        """Run ``docker compose ps`` and return the parsed service status table.

        :return: a list of rows, each a list of whitespace-trimmed column values.
        """
        self._check_file()

        command = ['docker', 'compose', '-f', self._df_name, 'ps']
        proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, cwd=self._df_dir)
        stdout, stderr = proc.communicate()
        a = stdout.decode()
        click.echo(a)
        return [[y.strip() for y in x.split('   ') if y.strip() != ''] for x in a.split('\n')[2:]]

    def new_instance(self, version: str | None = None, url: None | str = None, postgres_port: int = 5432,
                     eln_port: int = 4000, adminer_port: int = 8080, cwd=None):
        """Scaffold a new productive instance from the bundled templates into a directory.

        Renders the ``templates/productive`` tree into ``cwd``, filling in the URL, ports and
        selected image versions, then renames the generated ``docker-compose.yml`` to this
        manager's configured file name.

        :param version: image version tag; defaults to the latest available version.
        :param url: external base URL of the instance; defaults to ``http://localhost:<eln_port>``.
        :param postgres_port: host port for PostgreSQL.
        :param eln_port: host port for the ELN web service.
        :param adminer_port: host port for Adminer.
        :param cwd: target directory; created if missing, defaults to this manager's directory.
        :raises NotADirectoryError: if ``cwd`` exists but is not a directory.
        :raises ValueError: if ``cwd`` exists and is not empty.
        """
        images = self.get_image_of_versions(version)
        if cwd is None:
            cwd = self._df_dir
        cwd = os.path.abspath(cwd)
        if not os.path.isdir(cwd):
            if os.path.exists(os.path.isdir(cwd)):
                raise NotADirectoryError(f"{cwd} is not a directory")
            else:
                os.makedirs(cwd, exist_ok=True)
        if len(os.listdir(cwd)) != 0:
            raise ValueError(f'{cwd} is not empty!')
        if url is None:
            url = f'http://localhost:{eln_port}'
        for (is_file, name, content) in walk_productive_template(url, eln_port, postgres_port, adminer_port, **images):
            if is_file:
                with open(os.path.join(cwd, name), 'w+') as f:
                    f.write(content)
            else:
                os.makedirs(os.path.join(cwd, name))

        os.rename(os.path.join(cwd, 'docker-compose.yml'), os.path.join(cwd, self._df_name))

    def create_images(self):
        """Create the service containers without starting them (``docker compose up --no-start``).

        :return: the ``(stdout, stderr)`` tuple from the subprocess.
        """
        self._check_file()

        command = ['docker', 'compose', '-f', self._df_name, 'up', '--no-start']
        proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, cwd=self._df_dir)
        return proc.communicate()

    def up(self, eln: bool = False, db: bool = False, worker: bool = False, ketchersvc: bool = False,
           msconvert: bool = False, spectra: bool = False, converter: bool = False):
        """Start the instance, optionally restricting to the services flagged ``True``.

        If no service flag is set, all services are started; otherwise only the selected ones.

        :return: the subprocess stdout from ``docker compose start``.
        """
        return self._up(eln=eln, db=db, worker=worker, ketchersvc=ketchersvc, msconvert=msconvert, spectra=spectra,
                        converter=converter)

    def stop(self, eln: bool = False, db: bool = False, worker: bool = False, ketchersvc: bool = False,
             msconvert: bool = False, spectra: bool = False, converter: bool = False):
        """Stop the instance (containers preserved), optionally restricting to flagged services.

        If no service flag is set, all services are stopped; otherwise only the selected ones.
        """
        return self._stop(eln=eln, db=db, worker=worker, ketchersvc=ketchersvc, msconvert=msconvert, spectra=spectra,
                          converter=converter)

    def down(self, eln: bool = False, db: bool = False, worker: bool = False, ketchersvc: bool = False,
             msconvert: bool = False, spectra: bool = False, converter: bool = False):
        """Tear down the instance (``docker compose down``), optionally restricting to flagged services.

        If no service flag is set, all services are torn down; otherwise only the selected ones.
        """
        return self._down(eln=eln, db=db, worker=worker, ketchersvc=ketchersvc, msconvert=msconvert, spectra=spectra,
                          converter=converter)

    def _up(self, **kwargs):
        """Create the containers, then ``docker compose start`` (all or the truthy-flagged services)."""
        self._check_file()

        self.create_images()

        command_suffix = []
        if not all(kwargs.values()) and any(kwargs.values()):
            command_suffix = [k for (k, v) in kwargs.items() if v]

        command = ['docker', 'compose', '-f', self._df_name, 'start'] + command_suffix
        proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, cwd=self._df_dir)
        stdout, stderr = proc.communicate()
        return stdout

    def _stop(self, **kwargs):
        """Stop the selected (or all) services via :meth:`_stop_or_down`."""
        self._stop_or_down(stop_or_down='stop', **kwargs)

    def _down(self, **kwargs):
        """Tear down the selected (or all) services via :meth:`_stop_or_down`."""
        self._stop_or_down(stop_or_down='down', **kwargs)

    def _stop_or_down(self, stop_or_down, **kwargs):
        """Run ``docker compose stop|down`` for all or the truthy-flagged services.

        :raises ValueError: if ``stop_or_down`` is not ``'stop'`` or ``'down'``.
        """
        if stop_or_down not in ['stop', 'down']:
            raise ValueError('stop_or_down must be in stop, down')
        self._check_file()
        command_suffix = []
        if not all(kwargs.values()) and any(kwargs.values()):
            command_suffix = [k for (k, v) in kwargs.items() if v]

        command = ['docker', 'compose', '-f', self._df_name, stop_or_down] + command_suffix
        proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, cwd=self._df_dir)
        stdout, stderr = proc.communicate()
        return stdout

    def check_file(self) -> bool:
        """Return ``True`` if the configured compose file exists, ``False`` otherwise."""
        try:
            self._check_file()
            return True
        except FileNotFoundError:
            return False

    def _check_file(self) -> str:
        """Return the full path to the compose file, raising ``FileNotFoundError`` if absent."""
        df = str(os.path.join(self._df_dir, self._df_name))
        if not os.path.exists(df):
            raise FileNotFoundError(f"Docker-compose file does not exist: {df}")
        return df

    @staticmethod
    def backup(pguser='postgres', port=5432, host='localhost', pgpassword='postgres', database='chemotion',
               file_path=None):
        """Dump the PostgreSQL database to a ``.tar`` archive via ``pg_dump``.

        :param pguser: PostgreSQL user.
        :param port: PostgreSQL host port.
        :param host: PostgreSQL host.
        :param pgpassword: PostgreSQL password (set as ``PGPASSWORD``).
        :param database: database name to dump.
        :param file_path: output archive path; defaults to a timestamped file in the cwd.
        :return: the path to the written dump file.
        :raises ChildProcessError: if ``pg_dump`` exits with a non-zero status.
        """
        my_env = os.environ.copy()
        my_env["PGPASSWORD"] = pgpassword
        if file_path is None:
            file_path = os.path.abspath(
                os.path.join(os.getcwd(), f'./{database}_{datetime.now().strftime("%Y_%m_%d_%H_%M_%S")}.tar'))

        command = ['pg_dump', '-p', f'{port}', '-U', pguser, '-h', host, '-F', 't', '-f', file_path, database]
        proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=my_env)
        stdout, stderr = proc.communicate()
        if proc.returncode != 0:
            raise ChildProcessError(stderr)
        click.secho(f"Dumped {database} -> {file_path} !", fg='green', bg='white')
        return file_path

    @staticmethod
    def restore(file_path, pguser='postgres', port=5432, host='localhost', pgpassword='postgres', database='chemotion'):
        """Restore a ``pg_dump`` archive into a freshly recreated database.

        Drops the existing database (if any), recreates it, and runs ``pg_restore``.

        :param file_path: path to the dump archive to restore.
        :param pguser: PostgreSQL user.
        :param port: PostgreSQL host port.
        :param host: PostgreSQL host.
        :param pgpassword: PostgreSQL password (set as ``PGPASSWORD``).
        :param database: database name to recreate and restore into.
        :raises ChildProcessError: if ``createdb`` or ``pg_restore`` exits with a non-zero status.
        """
        file_path = os.path.abspath(file_path)

        my_env = os.environ.copy()
        my_env["PGPASSWORD"] = pgpassword
        command = ['dropdb', '-U', pguser, '-h', host, '-p', f'{port}', '-f', '--if-exists', database]
        proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=my_env)
        proc.communicate()
        if proc.returncode == 0:
            click.secho(f"Dropped {database}!", fg='red', bg='white')
        command = ['createdb', '-U', pguser, '-h', host, '-p', f'{port}', database]
        proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=my_env)
        proc.communicate()
        if proc.returncode != 0:
            raise ChildProcessError(f'createdb error: {proc.returncode}')
        click.secho(f"Recreated {database}!", fg='green', bg='white')
        command = ['pg_restore', '-U', pguser, '-h', host, '-p', f'{port}', '-d', database, file_path]
        proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=my_env)
        proc.communicate()
        if proc.returncode != 0:
            raise ChildProcessError(f'pg_restore error: {proc.returncode}')
        click.secho(f"Restored {file_path} -> {database}!", fg='green', bg='white')

    @staticmethod
    def get_versions():
        """Return the list of available Chemotion ELN image versions from Docker Hub.

        :return: version tags derived from the ``eln*`` image tags of ``ptrxyz/chemotion``.
        """
        res = requests.get('https://registry.hub.docker.com/v2/repositories/ptrxyz/chemotion/tags?page_size=1024')
        return [x['name'][4:] for x in res.json()['results'] if x['name'].startswith('eln')]

    @staticmethod
    def get_image_of_versions(version: None | str = None):
        """Return the per-service image references for a given Chemotion version.

        :param version: version tag; defaults to the latest available version.
        :return: a dict mapping service name to its ``ptrxyz/chemotion:<tag>`` image reference.
        """
        v_list = InstanceManager.get_versions()
        if version is None:
            version = v_list[0]
        res = requests.get('https://registry.hub.docker.com/v2/repositories/ptrxyz/chemotion/tags?page_size=1024')
        return dict(
            [(x['name'][:-(len(version) + 1)], f"ptrxyz/chemotion:{x['name']}") for x in res.json()['results'] if
             x['name'].endswith(version)])

    @staticmethod
    def insert_dataset(ols_term_id: str, pguser='postgres', port=5432, host='localhost', pgpassword='postgres',
                       database='chemotion'):
        """Insert a CHMO dataset class into the database, fetching its metadata from OLS.

        Looks up the term in EBI OLS4, then inserts a row into ``dataset_klasses`` with its
        label and definition.

        :param ols_term_id: CHMO term id (e.g. ``"CHMO:0000595"``).
        :param pguser: PostgreSQL user.
        :param port: PostgreSQL host port.
        :param host: PostgreSQL host.
        :param pgpassword: PostgreSQL password (set as ``PGPASSWORD``).
        :param database: database name to insert into.
        :raises ConnectionError: if the term cannot be found in OLS.
        """
        ols_term_id_num = ols_term_id.split(':')[-1]
        ols_link = f'https://www.ebi.ac.uk/ols4/api/v2/ontologies/chmo/classes/http%253A%252F%252Fpurl.obolibrary.org%252Fobo%252FCHMO_{ols_term_id_num}?lang=en&includeObsoleteEntities=t'
        res = requests.get(ols_link)
        if res.status_code != 200:
            raise ConnectionError(f'Unable to find: {ols_term_id} ({ols_link})')
        res_json = res.json()
        ols_term_id = res_json['curie']
        label = res_json['label']
        definition = res_json['definition']['value']
        created_at = datetime.now().strftime("%Y-%m-%d, %H:%M:%S.%f")
        # The OLS values are third-party data — pass them via psql variables (:'var'
        # quotes them safely) instead of interpolating into the SQL string, so
        # apostrophes in CHMO definitions or a malicious response cannot inject SQL.
        sql_command = ("INSERT INTO public.dataset_klasses (ols_term_id, label, \"desc\", created_by, created_at) "
                       "VALUES (:'ols_term_id', :'label', :'definition', 1, :'created_at')")
        my_env = os.environ.copy()
        my_env["PGPASSWORD"] = pgpassword
        command = ['psql', '-U', pguser, '-h', host, '-p', f'{port}', '-d', database,
                   '-v', f'ols_term_id={ols_term_id}',
                   '-v', f'label={label}',
                   '-v', f'definition={definition}',
                   '-v', f'created_at={created_at}']
        # the SQL is fed via stdin because psql does not apply variable
        # substitution to commands passed with -c
        proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=my_env)
        proc.communicate(input=sql_command.encode())
