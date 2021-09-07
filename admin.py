#!.venv/bin/python3

# Require python 3
import sys
if sys.version_info.major < 3:
    msg = "Requires python version 3; attempted with version '{}'".format( sys.version_info.major )
    raise UserWarning( msg )

# Configure logging
import logging
logger = logging.getLogger( __name__ )
logger.setLevel( logging.ERROR )
l_fmt = logging.Formatter( '%(levelname)s:%(funcName)s[%(lineno)d] %(message)s' )
l_handler = logging.StreamHandler()
l_handler.setFormatter( l_fmt )
logger.addHandler( l_handler )

# Finish imports
import argparse
import configparser
import csv
import datetime
import gzip
import os
import pathlib
import pprint
import re
import sqlite3
import subprocess
import tabulate
import yaml

# Hash to hold module level (global) data
resources = {}


def get_base():
    if not 'BASE' in resources:
        # Allow environment variable to override standard base install path
        resources['BASE'] = pathlib.Path( 
            os.getenv( 'PUP_ENC_DIR', default='/etc/puppetlabs/enc' )
            )
    return resources['BASE']


def get_cfg():
    if 'cfg' not in resources:
        BASE = get_base()
        cfg = configparser.ConfigParser()
        cfg.read( BASE / 'config.ini' )
        resources['cfg'] = cfg
    return resources['cfg']


def get_db_conf():
    ''' Load table config from yaml file
        Currently only use one table, specified by key "Nodes"
    '''
    if 'db_conf' not in resources:
        BASE = get_base()
        fn_default = 'tables.yaml'
        cfg = get_cfg()
        filename = pathlib.Path ( cfg.get( 'ENC', 'db_conf', fallback=fn_default ) )
        if not filename.is_absolute():
            filename = BASE / filename
        data = load_yaml_file( filename )
        resources['db_conf'] = data['Nodes']
    return resources['db_conf']


def get_db_table_name():
    if 'db_table_name' not in resources:
        resources['db_table_name'] = get_db_conf()['table_name']
    return resources['db_table_name']


def get_db_cols():
    if 'db_cols' not in resources:
        resources['db_cols'] = get_db_conf()['columns']
    return resources['db_cols']


def get_db_primary_key():
    if 'db_primary_key' not in resources:
        columns = get_db_cols()
        primary_key = None
        for col, attrs in columns.items():
            if 'PRIMARY KEY' in attrs:
                primary_key = col
                break
        if not primary_key:
            logger.critical( 'Failed to find DB primary key.' )
            raise SystemExit( 'Cannot proceed due to errors. Exiting...' )
        resources['db_primary_key'] = primary_key
    return resources['db_primary_key']


def get_bkup_dir():
    if 'bkup_dir' not in resources:
        cfg = get_cfg()
        default = '/var/backups/puppet_enc'
        resources['bkup_dir'] = pathlib.Path( cfg.get( 'ENC', 'bkup_dir', fallback=default ) )
    return resources['bkup_dir']


def load_yaml_file( filepath ):
    data = {}
    with filepath.open() as fh:
        data = yaml.safe_load( fh )
    return data


def load_csv_file( filepath ):
    ''' Return rows of OrderedDicts
    '''
    data = []
    with filepath.open() as fh:
        csv_handle = csv.DictReader( fh )
        data = [ row for row in csv_handle ]
    return data

def get_args():
    if 'args' not in resources:
        desc = "Manage Puppet ENC database"
        parser = argparse.ArgumentParser( description=desc )
        parser.add_argument( '--yaml', metavar='filename',
            help='''Source data for "add", "change", "delete".
                    Format is hash (key=fqdn, val=hash of node parameters).
                 ''')
        parser.add_argument( '--csv', metavar='filename',
            help='''Source data for "add", "change", "delete".
                    Format is CSV with headers.
                 ''' )
        parser.add_argument( '--debug', '-d', action='store_true' )
        parser.add_argument( '--verbose', '-v', action='store_true' )
        parser.add_argument( 'nodelist', nargs=argparse.REMAINDER,
            help="One or more node names/regex-patterns to operate on." )
    
        # Create arg parser group for DB table columns
        cols_group = parser.add_argument_group( 'Specifying node parameters',
            description='''Set one or more parameters for all nodes in NODELIST.
                           Used with --add and --change.
                           Only relevant for cmdline changes 
                           (ignored when --yaml or --csv is present.)
                        ''' )
        columns = get_db_cols()
        db_primary_key = get_db_primary_key()
        for k in columns:
            long_opt = '--' + k
            cols_group.add_argument( long_opt )
    
        # Actions
        action_group = parser.add_argument_group( 'Action', 
            description='If no action given, prints YAML for the node given.' )
        action_group.add_argument( '--add', dest='action',
            action='store_const', const='add',
            help='''Add new nodes. Data is taken from --yaml or cmdline.
                 ''')
        action_group.add_argument( '--change', '--ch', dest='action',
            action='store_const', const='change',
            help='''Make one or more changes to specified nodes.
                    Data is taken from --yaml or cmdline.
                 ''')
        action_group.add_argument( '--delete', '--del', dest='action',
            action='store_const', const='delete',
            help='''Delete nodes in --yaml or matching nodelist.
                 ''')
        action_group.add_argument( '--list', '--ls', '-l', dest='action',
            action='store_const', const='list',
            help='''List rows matching nodelist, or all rows if nodelist is empty.
                 ''')
        action_group.add_argument( '--lookup', dest='action',
            action='store_const', const='lookup',
            help='''Lookup a single node by unique primary key and
                    return valid yaml for puppetserver.
                    This is the default action.
                 ''')
        action_group.add_argument( '--production', '--prod', dest='action',
            action='store_const', const='production',
            help='''Shortcut for "--chnode --environment production"
                 ''')
        action_group.add_argument( '--topic',
            help='''Shortcut for "--chnode --environment TOPIC"
                 ''' )
        action_group.add_argument( '--bkup', dest='action',
            action='store_const', const='bkup',
            help='''Make a backup, stored in "bkup_dir" as defined in config.
                 ''')
        action_group.add_argument( '--restore', dest='action', metavar='filename',
            action='store_const', const='restore',
            help='''Restore database from a backup.
                    Requires a filename to use as restore source.
                 ''')
        action_group.add_argument( '--init', dest='action',
            action='store_const', const='init',
            help='''Create a new database (backup old one first if it exists).
                 ''')
        action_group.add_argument( '--mkyaml', dest='action',
            action='store_const', const='mkyaml',
            help='''Print a yaml template.
                 ''')
        action_group.add_argument( '--mkcsv', dest='action',
            action='store_const', const='mkcsv',
            help='''Print a csv template.
                 ''')
    
        # Sane defaults for cmdline options
        defaults = {
            'action': 'lookup',
        }
        parser.set_defaults( **defaults )
        args = parser.parse_args()
        resources['args'] = args

        # Post processing
        if args.verbose:
            logger.setLevel( logging.INFO )
        if args.debug:
            logger.setLevel( logging.DEBUG )
        if args.topic:
            args.action = 'topic'

    return resources['args']


def get_db_conn():
    if not 'db_conn' in resources:
        BASE = get_base()
        cfg = get_cfg()
        default = BASE / 'puppet_enc.sqlite'
        filename = pathlib.Path( cfg.get( 'ENC', 'db_file', fallback=default ) )
        if not filename.is_absolute():
            filename = BASE / filename
        try:
            conn = sqlite3.connect( str( filename ) )
        except (sqlite3.Error) as e:
            raise e
        conn.row_factory = sqlite3.Row
        resources['db_conn'] = conn
    return resources['db_conn']


def run_sql( sqlcmd, params=[] ):
    conn = get_db_conn()
    logger.info( f"{sqlcmd} + {pprint.pformat(params)}", )
    return conn.execute( sqlcmd, params )


def run_sql_transaction( cmdlist ):
    ''' Run cmds in cmdlist inside a transaction.
        cmdlist is a list of dicts, such as:
        cmdlist = [ { 'cmd':cmd, 'parameters':vals },
                    ...
                  ]
    '''
    conn = get_db_conn()
    with conn:
        for stmt in cmdlist:
            cmd = stmt['cmd']
            params = stmt['parameters']
            logger.info( f"{cmd} + {','.join(params)}", )
            conn.execute( cmd, params )


def drop_table():
    table_name = get_db_table_name()
    run_sql( f'DROP TABLE IF EXISTS {table_name};' )


def create_table():
    table_name = get_db_table_name()
    columns = get_db_cols()
    col_str_parts = []
    for tname, attrlist in columns.items():
        col_str_parts.append( ' '.join( [ tname, *attrlist ] ) )
    sql = f'CREATE TABLE {table_name} ( ' \
        + ', '.join( col_str_parts ) \
        + ' );'
    run_sql( sql )
        

def parse_node_changes():
    ''' Get node change data from yaml, csv, or cmdline
        Return dict, formatted as if it came from a Yaml file
    '''
    args = get_args()
    columns = get_db_cols()
    db_primary_key = get_db_primary_key()
    data = {}
    if args.yaml:
        filepath = pathlib.Path( args.yaml )
        data = load_yaml_file( filepath )
    elif args.csv:
        filepath = pathlib.Path( args.csv )
        rows = load_csv_file( filepath )
        # convert rows into dict with db_primary_key as dict key
        for ordered_dict in rows:
            data[ ordered_dict[db_primary_key] ] = ordered_dict
    else:
        for node in args.nodelist:
            # construct data dict from cmdline args
            data[ node ] = {}
            for col in columns:
                val = getattr( args, col )
                if val:
                    data[ node ][ col ] = val
    validate_node_change_data( data )
    logger.debug( f"Change Data: '{pprint.pformat(data)}'" )
    return data


def validate_node_change_data( data ):
    ''' Transform incoming data as follows:
        environment: replace '/[^A-Za-z0-9_]/' with '_'
                     (per r10k invalid_branches setting)
    '''
    transformations = {
        'environment': { 'func': replace_non_word_chars,
                         'args': [],
                         'kwargs': {},
                       },
    }
    for node,column_data in data.items():
        for col,change in transformations.items():
            if col in column_data:
                f = change['func']
                a = change['args']
                k = change['kwargs']
                old_val = data[node][col]
                new_val = f( old_val, *a, **k )
                data[node][col] = new_val


def replace_non_word_chars( string ):
    r = re.compile( '[^A-Za-z0-9_]')
    return r.sub( '_', string )


def do_bkup():
    bkup_dir = get_bkup_dir()
    # ensure bkup dir exists
    bkup_dir.mkdir( parents=True, exist_ok=True )
    # create bkup filename
    timestamp = str( datetime.datetime.now().strftime( '%Y%m%d-%H%M%S' ) )
    bkup_fn = bkup_dir / f'{timestamp}.sql.gz'
    # populate bkup file with sql data
    conn = get_db_conn()
    with gzip.open( bkup_fn, 'wt' ) as fh:
        for line in conn.iterdump():
            fh.write( f'{line}\n' )


def do_restore():
    args = get_args()
    if len( args.nodelist ) < 1:
        logger.critical( 'Missing restore filename for action "restore"' )
        raise SystemExit( 'Cannot proceed due to errors. Exiting...' )
    elif len( args.nodelist ) > 1:
        logger.critical( 'Expecting just one file as restore source' )
        raise SystemExit( 'Cannot proceed due to errors. Exiting...' )
    raw_fn = pathlib.Path( args.nodelist[0] )
    tgt_fn = raw_fn
    if not raw_fn.is_absolute():
        # prepend bkup_dir if raw_fn is not absolute
        tgt_fn = get_bkup_dir() / raw_fn
    with gzip.open( tgt_fn, 'rt' ) as fh:
        cmdstr = ''.join( fh.readlines() )
    drop_table()
    conn = get_db_conn()
    conn.executescript( cmdstr )
    do_bkup()


def do_init():
    drop_table()
    create_table()
    do_bkup()


def do_add():
    # Get node changes as data hash
    node_changes = parse_node_changes()
    if len( node_changes ) < 1:
        # If no nodes given AND args.<primary_key> has a value, use value of primary_key as node
        args = get_args()
        primary_key = get_db_primary_key()
        primary_value = getattr( args, primary_key )
        if not primary_value:
            msg = f'Missing {primary_key}'
            logger.error( msg )
            raise SystemExit()
        args.nodelist = [ primary_value ]
        node_changes = parse_node_changes()
    # Create sql insert stmts from node_changes hash
    table_name = get_db_table_name()
    sqlcmds = []
    for node,column_data in node_changes.items():
        cols = []
        vals = []
        for col,val in column_data.items():
            cols.append( col )
            vals.append( val )
        colnames = ','.join( cols )
        valnames = ','.join( [ '?' for c in cols ] )
        cmd = f'''INSERT INTO {table_name} ({colnames})
                  VALUES ({valnames})
               '''
        sqlcmds.append( { 'cmd':cmd, 'parameters':vals } )
    # Execute sql cmds as a transaction
    run_sql_transaction( sqlcmds )
    do_bkup()


def do_change():
    ''' Nodes must exactly match by fqdn
    '''
    # Get node changes as data hash
    node_changes = parse_node_changes()
    # Create sql update stmts from node_changes hash
    table_name = get_db_table_name()
    primary_key = get_db_primary_key()
    sqlcmds = []
    for node,column_data in node_changes.items():
        cols = []
        vals = []
        for col,val in column_data.items():
            cols.append( f'{col} = ?' )
            vals.append( val )
        colnames = ','.join( cols )
        vals.append( node )
        cmd = f'''UPDATE {table_name} SET {colnames}
                  WHERE {primary_key} = ?
               '''
        sqlcmds.append( { 'cmd':cmd, 'parameters':vals } )
    # Execute sql cmds as a transaction
    run_sql_transaction( sqlcmds )
    do_bkup()


def do_delete():
    ''' Nodes must exactly match by fqdn
    '''
    # Get node changes as data hash
    node_changes = parse_node_changes()
    # Create sql delete stmts from node_changes hash
    table_name = get_db_table_name()
    primary_key = get_db_primary_key()
    sqlcmds = []
    for node in node_changes:
        cmd = f'''DELETE FROM {table_name}
                  WHERE {primary_key} = ?
               '''
        sqlcmds.append( { 'cmd':cmd, 'parameters':[node] } )
    # Execute sql cmds as a transaction
    run_sql_transaction( sqlcmds )
    do_bkup()


def do_list():
    args = get_args()
    table_name = get_db_table_name()
    db_cols = get_db_cols()
    primary_key = get_db_primary_key()
    # list of cols, starting with priamary_key, then the rest in sorted order
    cols = [ primary_key ] + sorted( [ col for col in db_cols if col != primary_key ] )
    colnames = ','.join( cols )
    sqlparts = [ f'SELECT {colnames} FROM {table_name}' ]
    if len( args.nodelist ) > 0:
        sqlparts.append( 'WHERE (' )
        where_parts = []
        for node in args.nodelist:
            where_parts.append( f'{primary_key} LIKE "%{node}%"' )
        sqlparts.append( ' OR '.join( where_parts ) )
        sqlparts.append( ')' )
    sqlparts.append( f' ORDER BY {primary_key} ASC')
    cur = run_sql( ' '.join( sqlparts ) )
    rows = cur.fetchall()
    tablefmt = 'simple'
    print( tabulate.tabulate( rows, headers=cols, tablefmt=tablefmt ) )


def do_lookup():
    args = get_args()
    cfg = get_cfg()
    role_model = cfg.get( 'ENC', 'role_model', fallback='module' )
    logger.debug( f"Role model: '{role_model}'" )
    if role_model not in ( 'module', 'hiera' ):
        raise UserWarning( f"Invalid role_model '{role_model}'" )
    node = None
    db_data = {}
    if len ( args.nodelist ) == 1:
        node = args.nodelist[0]
        table_name = get_db_table_name()
        primary_key = get_db_primary_key()
        cmd = f'SELECT * FROM {table_name} WHERE {primary_key} = ?'
        try:
            cur = run_sql( cmd, [node] )
            r = cur.fetchone()
            if r:
                db_data = { k: str(r[k]) for k in r.keys() }
        except (sqlite3.Error) as e:
            raise UserWarning( f"SQL error looking up hostname '{node}'" )
        # Build output data hash
        enc = { 'parameters': { 'enc_hostname': node } }
        if len( db_data ) > 1:
            enc['environment'] = db_data.pop( 'environment', 'production' )
            enc['parameters'].update( db_data )
            # add "classes" key only if roles defined in a module
            if role_model == 'module':
                try:
                    role = db_data[ 'role' ]
                except ( KeyError ) as e:
                    role = 'role_not_found'
                enc['classes'] = [ f'role::{role}' ]
        else:
            # this is an error state, so set classes without regard to role_model
            enc['classes'] = [ 'role::hostname_not_found' ]
        enc.pop('fqdn', None) # ensure "fqdn" never exists in yaml output
        print( '---' )
        print( yaml.dump( enc ) )
    else:
        raise UserWarning( f'Error: missing or ill-formatted nodename' )


def do_production():
    ''' Set environment to 'production' for nodes in nodelist
    '''
    args = get_args()
    args.environment = 'production'
    do_change()


def do_test():
    ''' Set environment to 'test' for nodes in nodelist
    '''
    args = get_args()
    args.environment = 'test'
    do_change()


def do_topic():
    ''' Set environment to the given topic for nodes in nodelist
    '''
    args = get_args()
    args.environment = args.topic
    do_change()


def do_mkyaml():
    cols = get_db_cols()
    primary_key = get_db_primary_key()
    lines = [ '---', f'<{primary_key.upper()}>:' ]
    lines.extend( [ f'    {col}: <VALUE>' for col in cols ] )
    lines.append( '''
# When adding new nodes, omitted parameters will use database defaults.
# When chagning nodes, omitted parameters will retain current value.
# Note the parameter matching the database primary key ("fqdn", by default)
# is redundant and can be omitted unless intent is to change that value.
''' )
    print( '\n'.join( lines ) )


def do_mkcsv():
    cols = get_db_cols()
    lines = [ ','.join( cols ) ]
    names = [ f'<{col.upper()}>' for col in cols ]
    lines.append( ','.join( names ) )
    print( '\n'.join( lines ) )


def run():
    # Process cmdline args
    args = get_args()
    logger.debug( args )

    # Take action
    funcname = 'do_' + args.action
    try:
        func = globals()[funcname]
    except (KeyError) as e:
        raise SystemExit( f"Undefined action: '{args.action}'" )
    func()

if __name__ == '__main__':
    run()
