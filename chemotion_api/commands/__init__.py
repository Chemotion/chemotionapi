import os
import subprocess
from datetime import datetime
from .creator import walk_productive_template

import click
import requests

from .updater import update_images, update_eln_port, update_db_port, get_eln_port, get_db_port


class InstanceManager:

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
        df = self._check_file()
        return get_eln_port(df)

    @property
    def db_port(self):
        df = self._check_file()
        return get_db_port(df)

    def update(self, version=None):
        df = self._check_file()
        images = self.get_image_of_versions(version)
        update_images(df, **images)

    def update_port(self, eln_port):
        df = self._check_file()
        update_eln_port(df, eln_port)

    def update_db_port(self, postgresql_port):
        df = self._check_file()
        update_db_port(df, postgresql_port)

    def check(self):
        self._check_file()

        command = ['docker', 'compose', '-f', self._df_name, 'ps']
        proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, cwd=self._df_dir)
        stdout, stderr = proc.communicate()
        a = stdout.decode()
        click.echo(a)
        return [[y.strip() for y in x.split('   ') if y.strip() != ''] for x in a.split('\n')[2:]]

    def new_instance(self, version: str | None = None, url: None | str = None, postgres_port: int = 5432,
                     eln_port: int = 4000, adminer_port: int = 8080, cwd=None):
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
        self._check_file()

        command = ['docker', 'compose', '-f', self._df_name, 'up', '--no-start']
        proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, cwd=self._df_dir)
        return proc.communicate()

    def up(self, eln: bool = False, db: bool = False, worker: bool = False, ketchersvc: bool = False,
           msconvert: bool = False, spectra: bool = False, converter: bool = False):
        return self._up(eln=eln, db=db, worker=worker, ketchersvc=ketchersvc, msconvert=msconvert, spectra=spectra,
                        converter=converter)

    def stop(self, eln: bool = False, db: bool = False, worker: bool = False, ketchersvc: bool = False,
             msconvert: bool = False, spectra: bool = False, converter: bool = False):
        return self._stop(eln=eln, db=db, worker=worker, ketchersvc=ketchersvc, msconvert=msconvert, spectra=spectra,
                          converter=converter)

    def down(self, eln: bool = False, db: bool = False, worker: bool = False, ketchersvc: bool = False,
             msconvert: bool = False, spectra: bool = False, converter: bool = False):
        return self._down(eln=eln, db=db, worker=worker, ketchersvc=ketchersvc, msconvert=msconvert, spectra=spectra,
                          converter=converter)

    def _up(self, **kwargs):
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
        self._stop_or_down(stop_or_down='stop', **kwargs)

    def _down(self, **kwargs):
        self._stop_or_down(stop_or_down='down', **kwargs)

    def _stop_or_down(self, stop_or_down, **kwargs):
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
        try:
            self._check_file()
            return True
        except FileNotFoundError:
            return False

    def _check_file(self) -> str:
        df = str(os.path.join(self._df_dir, self._df_name))
        if not os.path.exists(df):
            raise FileNotFoundError(f"Docker-compose file dose not exist: {df}")
        return df

    @staticmethod
    def backup(pguser='postgres', port=5432, host='localhost', pgpassword='postgres', database='chemotion',
               file_path=None):
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
        res = requests.get('https://registry.hub.docker.com/v2/repositories/ptrxyz/chemotion/tags?page_size=1024')
        return [x['name'][4:] for x in res.json()['results'] if x['name'].startswith('eln')]

    @staticmethod
    def get_image_of_versions(version: None | str = None):
        v_list = InstanceManager.get_versions()
        if version is None:
            version = v_list[0]
        res = requests.get('https://registry.hub.docker.com/v2/repositories/ptrxyz/chemotion/tags?page_size=1024')
        return dict(
            [(x['name'][:-(len(version) + 1)], f"ptrxyz/chemotion:{x['name']}") for x in res.json()['results'] if
             x['name'].endswith(version)])

    @staticmethod
    def insert_dataset(ols_term_id: str, label: str, pguser='postgres', port=5432, host='localhost', pgpassword='postgres', database='chemotion'):
        created_at = datetime.now().strftime("%Y-%m-%d, %H:%M:%S.%f")
        sql_command = f"INSERT INTO public.dataset_klasses (ols_term_id, label, \"desc\", created_by, created_at) VALUES ('{ols_term_id}', '{label}', '{label}', 1, '{created_at}')";
        my_env = os.environ.copy()
        my_env["PGPASSWORD"] = pgpassword
        command = ['psql', '-U', pguser, '-h', host, '-p', f'{port}', '-d', database, '-c', sql_command]
        proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=my_env)
        proc.communicate()
