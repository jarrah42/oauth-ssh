import os
import sys
import click
import requests

CTX_CLIENT_ID = 'client_id'
CTX_CLIENT_SECRET = 'client_secret'
CTX_ACCESS_TOKEN = 'access_token'

GLOBUS_AUTH_ENVS = {'preview':     'https://auth.preview.globus.org/v2',
                    'staging':     'https://auth.staging.globuscs.info/v2',
                    'test':        'https://auth.test.globuscs.info/v2',
                    'integration': 'https://auth.integration.globuscs.info/v2',
                    'sandbox':     'https://auth.sandbox.globuscs.info/v2',
                    'production':  'https://auth.globus.org/v2'}

GLOBUS_AUTH_ENDPOINT = GLOBUS_AUTH_ENVS['production']
GLOBUS_SDK_ENVIRONMENT = os.environ.get('GLOBUS_SDK_ENVIRONMENT')
if GLOBUS_SDK_ENVIRONMENT in GLOBUS_AUTH_ENVS:
    GLOBUS_AUTH_ENDPOINT = GLOBUS_AUTH_ENVS[GLOBUS_SDK_ENVIRONMENT]

SSH_SCOPE_SUFFIX = "ssh"
SSH_SCOPE_FORMAT = "https://auth.globus.org/scopes/%s/" + SSH_SCOPE_SUFFIX

CONFIG_FILE = '/etc/globus/globus-ssh.conf'
CONFIG_KEY_ID = 'auth_client_id'
CONFIG_KEY_SECRET = 'auth_client_secret'


def get_config_value(file, key):
    try:
        with open(file, 'r') as config_file:
            contents = [line.rstrip().strip() for line in config_file]
        return [x for x in contents if x.startswith(key)][0].split()[1]
    except:
        return None


OPT_CLIENT_ID = '--client_id'
OPT_CLIENT_SECRET = '--client_secret'
ENV_CLIENT_ID = 'CLIENT_ID'
ENV_CLIENT_SECRET = 'CLIENT_SECRET'

MISSING_OPT_ERR_MSG = (
    "Missing one or both of client id and client secret. Use the command line"
    "\noptions {0} and {1} or the env variables {2} and\n{3} or place the "
    "values in {4} as\n{5} and {6}" . format(OPT_CLIENT_ID,
                                             OPT_CLIENT_SECRET,
                                             ENV_CLIENT_ID,
                                             ENV_CLIENT_SECRET,
                                             CONFIG_FILE,
                                             CONFIG_KEY_ID,
                                             CONFIG_KEY_SECRET))


@click.group()
@click.pass_context
@click.option(OPT_CLIENT_ID,
              envvar=ENV_CLIENT_ID,
              help='Globus Auth client ID for your SSH service')
@click.option(OPT_CLIENT_SECRET,
              envvar=ENV_CLIENT_SECRET,
              help='Globus Auth client secret for your SSH service')

def entry_point(ctx, client_id, client_secret):
    """This script allows you to register a fully qualified domain name (FQDN)
       with your SSH for Globus Auth service so that users of the globus-ssh
       client can access it as 'globus-ssh <FQDN>'.
    """
    ctx.obj = {}

    if not client_id:
        client_id = get_config_value(CONFIG_FILE, CONFIG_KEY_ID)

    if not client_secret:
        client_secret = get_config_value(CONFIG_FILE, CONFIG_KEY_SECRET)

    if not client_id or not client_secret:
        if os.access(CONFIG_FILE, os.R_OK) is False:
            click.echo("WARNING: can not read {0}\n".format(CONFIG_FILE))

        click.echo("ERROR: " + MISSING_OPT_ERR_MSG)
        sys.exit(1)

    ctx.obj[CTX_CLIENT_ID] = client_id
    ctx.obj[CTX_CLIENT_SECRET] = client_secret


def print_friendly_auth_err_msg(auth_reply):
    errors = auth_reply.json()['errors'][0]

    if "code" in errors and errors['code'] == "UNAUTHORIZED":
        click.echo("Authorization failed. Please check your client ID and "
                   "secret and try again.")
        return

    click.echo(auth_reply.text)


@click.command()
@click.argument('fqdn')
@click.pass_context
def register(ctx, fqdn):
    client_id = ctx.obj[CTX_CLIENT_ID]
    client_secret = ctx.obj[CTX_CLIENT_SECRET]

    clients_url = GLOBUS_AUTH_ENDPOINT + '/api/clients'
    r = requests.get(clients_url, auth=(client_id, client_secret))

    if r.status_code != requests.codes.ok:
        print_friendly_auth_err_msg(r)
        sys.exit(1)

    clients = r.json()['clients']
    clients = filter(lambda x: x['id'] == ctx.obj[CTX_CLIENT_ID], clients)
    clients = filter(lambda x: fqdn in x['fqdns'], clients)

    if len(clients) == 0:
        url = GLOBUS_AUTH_ENDPOINT + '/api/clients/' + client_id + '/fqdns'
        r = requests.post(url,
                          auth=(client_id, client_secret),
                          json={'fqdn': fqdn})

        if r.status_code != requests.codes.ok:
            print_friendly_auth_err_msg(r)
            sys.exit(1)

    r = requests.get(GLOBUS_AUTH_ENDPOINT + '/api/scopes',
                     auth=(ctx.obj[CTX_CLIENT_ID], ctx.obj[CTX_CLIENT_SECRET]))

    if r.status_code != requests.codes.ok:
        print_friendly_auth_err_msg(r)
        sys.exit(1)

    scopes = r.json()['scopes']
    scopes = filter(lambda x: x['client'] == ctx.obj[CTX_CLIENT_ID], scopes)
    scope_string = (SSH_SCOPE_FORMAT % ctx.obj[CTX_CLIENT_ID])
    scopes = filter(lambda x: x['scope_string'] == scope_string, scopes)

    if len(scopes) == 0:
        url = GLOBUS_AUTH_ENDPOINT + '/api/clients/' + client_id + '/scopes'
        body = {'scope': {'name': 'SSH',
                          'description': 'Allow SSH access to host',
                          'scope_suffix': SSH_SCOPE_SUFFIX}}
        r = requests.post(url, auth=(client_id, client_secret), json=body)

        if r.status_code != requests.codes.ok:
            print_friendly_auth_err_msg(r)
            sys.exit(1)

    click.echo("Success")


entry_point.add_command(register)

if __name__ == '__main__':
    entry_point()
