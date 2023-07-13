from snowflake.snowpark import Session
import os
from typing import Optional

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric.types import PRIVATE_KEY_TYPES
from cryptography.hazmat.primitives import serialization


# Class to store a singleton connection option
class SnowflakeConnection(object):
    _connection = None

    @property
    def connection(self) -> Optional[Session]:
        return type(self)._connection

    @connection.setter
    def connection(self, val):
        type(self)._connection = val


def _get_private_key() -> PRIVATE_KEY_TYPES:
    with open(os.environ['SNOWFLAKE_P8_FILE'], "rb") as key:
        p_key= serialization.load_pem_private_key(
            key.read(),
            password=os.environ['SNOWSQL_PRIVATE_KEY_PASSPHRASE'].encode(),
            backend=default_backend()
        )
        return p_key


def _get_connection_params(private_key: PRIVATE_KEY_TYPES) -> dict:
    pkb = private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
        )
    return {
        "account": os.environ['SNOWFLAKE_ACCOUNT'],
        "user": os.environ['SNOWFLAKE_USER'],
        "role": os.environ['SNOWFLAKE_ROLE'],
        "private_key": pkb,
        "warehouse": os.environ['SNOWFLAKE_WAREHOUSE'],
        "database": os.environ['SNOWFLAKE_DATABASE'],
        "schema": os.environ['SNOWFLAKE_SCHEMA'],
    }


def _get_key_pair_auth_session() -> Session:
    private_key = _get_private_key()
    connection_params = _get_connection_params(private_key)
    return Session.builder.configs(connection_params).create()


# Function to return a configured Snowpark session
def get_snowpark_session() -> Session:
    # if running in snowflake
    if SnowflakeConnection().connection:
        # Not sure what this does?
        session = SnowflakeConnection().connection
    elif "SNOWFLAKE_P8_FILE" in os.environ:
        SnowflakeConnection().connection = _get_key_pair_auth_session()
    # if running locally with a config file
    # TODO: Look for a creds.json style file. This should be the way all snowpark
    # related tools work IMO
    # if using snowsql config, like snowcli does
    elif os.path.exists(os.path.expanduser('~/.snowsql/config')):
        snowpark_config = get_snowsql_config()
        SnowflakeConnection().connection = Session.builder.configs(snowpark_config).create()
    # otherwise configure from environment variables
    elif "SNOWSQL_ACCOUNT" in os.environ:
        snowpark_config = {
            "account": os.environ["SNOWSQL_ACCOUNT"],
            "user": os.environ["SNOWSQL_USER"],
            "password": os.environ["SNOWSQL_PWD"],
            "role": os.environ["SNOWSQL_ROLE"],
            "warehouse": os.environ["SNOWSQL_WAREHOUSE"],
            "database": os.environ["SNOWSQL_DATABASE"],
            "schema": os.environ["SNOWSQL_SCHEMA"]
        }
        SnowflakeConnection().connection = Session.builder.configs(snowpark_config).create()

    if SnowflakeConnection().connection:
        return SnowflakeConnection().connection  # type: ignore
    else:
        raise Exception("Unable to create a Snowpark session")


# Mimic the snowcli logic for getting config details, but skip the app.toml processing
# since this will be called outside the snowcli app context.
# TODO: It would be nice to get rid of this entirely and always use creds.json but
# need to update snowcli to make that happen
def get_snowsql_config(
    connection_name: str = 'dev',
    config_file_path: str = os.path.expanduser('~/.snowsql/config'),
) -> dict:
    import configparser

    snowsql_to_snowpark_config_mapping = {
        'account': 'account',
        'accountname': 'account',
        'username': 'user',
        'password': 'password',
        'rolename': 'role',
        'warehousename': 'warehouse',
        'dbname': 'database',
        'schemaname': 'schema'
    }
    try:
        config = configparser.ConfigParser(inline_comment_prefixes="#")
        connection_path = 'connections.' + connection_name

        config.read(config_file_path)
        session_config = config[connection_path]
        # Convert snowsql connection variable names to snowcli ones
        session_config_dict = {
            snowsql_to_snowpark_config_mapping[k]: v.strip('"')
            for k, v in session_config.items()
        }
        return session_config_dict
    except Exception:
        raise Exception(
            "Error getting snowsql config details"
        )
