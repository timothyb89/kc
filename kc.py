#!/usr/bin/env python

import logging
import os
import subprocess
import sys

from argparse import ArgumentParser
from functools import wraps

import yaml


logging.basicConfig(level=logging.WARN)
logger = logging.getLogger(__name__)

verbs = []


def verb(name, aliases=None, description=None):
    if not aliases:
        aliases = []

    def verb_decorator(func):
        verbs.append({
            'name': name,
            'aliases': aliases,
            'description': description,
            'function': func
        })

        @wraps(func)
        def func_wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        return func_wrapper

    return verb_decorator


def resolve_config(from_dir=None):
    if from_dir is None:
        from_dir = os.getcwd()

    for name in ['.kc.yml', '.kc.yaml']:
        candidate = os.path.join(from_dir, name)
        if os.path.exists(candidate):
            return candidate

    next_dir = os.path.dirname(from_dir)
    if next_dir == from_dir:
        return None

    return resolve_config(next_dir)


def update_if_exists(src, src_key, dest, dest_key):
    if src_key in src:
        dest[dest_key] = os.environ[src_key]


def set_environ_config(config):
    env = {}

    update_if_exists(os.environ, 'KC_NAMESPACE', config, 'namespace')
    update_if_exists(os.environ, 'KC_KUBECONFIG', config['env'], 'KUBECONFIG')
    update_if_exists(os.environ, 'KC_HTTP_PROXY', config['env'], 'HTTP_PROXY')
    update_if_exists(os.environ, 'KC_HTTPS_PROXY', config['env'], 'HTTPS_PROXY')
    update_if_exists(os.environ, 'KC_NO_PROXY', config['env'], 'NO_PROXY')

    return env


def load_config():
    config = {}
    config_path = resolve_config()

    logger.debug('Loading config from: %r', config_path)

    if config_path:
        with open(config_path, 'r') as f:
            config.update(yaml.load(f))

    if 'env' not in config:
        config['env'] = {}

    set_environ_config(config)

    return config


def get_environment(config):
    if config.get('inherit_env', True) is True:
        env = os.environ.copy()
    else:
        env = {}

    env.update(config['env'])
    return env


@verb('select',
      aliases=['sel', 's'],
      description='Find an exact resource name based on labels')
def handle_select(config, remaining_args):
    parser = ArgumentParser(prog='kc select',
                            description='Finds an exact resource '
                                        'name based on labels')
    parser.add_argument('--resource', '-r', default='pod',
                        help='The resource type (default: pod)')
    parser.add_argument('selectors', nargs='+',
                        help='One or more key=value selectors, space-separated')
    args = parser.parse_args(remaining_args)

    cmd_path = config.get('kubectl_path', 'kubectl')
    cmd = [cmd_path]
    if 'namespace' in config:
        cmd.extend(['-n', config['namespace']])

    cmd.extend(['get', args.resource, '-l', ','.join(args.selectors)])
    cmd.append('-o=jsonpath={.items[*].metadata.name}')

    p = subprocess.Popen(cmd, env=get_environment(config))
    return p.wait()


@verb('nodeport', aliases=['np'], description='Resolve a service nodeport')
def handle_nodeport(config, remaining_args):
    parser = ArgumentParser(prog='kc nodeport',
                            description='Resolves a service nodeport')
    parser.add_argument('service_name',
                        help='The name of the service to query.')
    parser.add_argument('port', nargs='?', default='0',
                        help='The port name or index (default: 0)')
    args = parser.parse_args(remaining_args)

    cmd_path = config.get('kubectl_path', 'kubectl')
    cmd = [cmd_path]
    if 'namespace' in config:
        cmd.extend(['-n', config['namespace']])

    cmd.extend(['get', 'service', args.service_name])

    try:
        port = int(args.port)
        cmd.append('-o=jsonpath={.spec.ports[%d].nodePort}' % port)
    except ValueError:
        cmd.append('-o=jsonpath={.spec.ports[?(@.name=="%s")].nodePort}' % args.port)

    p = subprocess.Popen(cmd, env=get_environment(config))
    return p.wait()


#@verb('update', aliases=['up'], description='Updates a configmap in-place')
def handle_update_configmap(config, remaining_args):
    print 'TODO'
    return True


#@verb('bash', aliases=['sh'], description='Open an interactive terminal in a pod')
def handle_bash(config, remaining_args):
    print 'TODO'
    return True


def handle_special(config, name, remaining_args):
    verb_defs = filter(lambda v: name == v['name'] or name in v['aliases'], verbs)
    if verb_defs:
        return verb_defs[0]['function'](config, remaining_args)
    else:
        return None


def handle_passthrough(config, user_args):
    cmd_path = config.get('kubectl_path', 'kubectl')
    args = [cmd_path]

    if 'namespace' in config:
        args.extend(['-n', config['namespace']])

    args.extend(user_args)

    p = subprocess.Popen(args, env=get_environment(config))
    return p.wait()


def print_kc_help():
    print '-----'
    print 'kc wraps kubectl to provide extra functionality.'
    print ''

    print 'Additional Commands:'
    for verb_def in verbs:
        if len(verb_def['aliases']) > 0:
            aka = ' (aka %s)' % ','.join(verb_def['aliases'])
        else:
            aka = ''

        print '  %-15s%s%s' % (verb_def['name'], verb_def['description'] or '', aka)


def main():
    if 'KC_DEBUG' in os.environ:
        logger.setLevel(logging.DEBUG)

    config = load_config()
    user_args = sys.argv[1:]

    if not user_args or user_args[0] in ('help', '--help', '-h'):
        handle_passthrough(config, user_args)
        print_kc_help()
        sys.exit(0)

    special_ret = handle_special(config, user_args[0], user_args[1:])
    if special_ret is None:
        sys.exit(handle_passthrough(config, user_args))
    else:
        sys.exit(special_ret)


if __name__ == '__main__':
    main()
