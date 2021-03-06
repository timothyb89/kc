#!/usr/bin/env python

from __future__ import print_function

import logging
import os
import subprocess
import sys
import urlparse
import webbrowser

from argparse import ArgumentParser, REMAINDER
from functools import wraps

import yaml


logging.basicConfig(level=logging.WARN)
logger = logging.getLogger(__name__)

verbs = []


class CaptureException(Exception):
    def __init__(self, retcode, stdout, stderr):
        super(CaptureException, self).__init__(stderr)

        self.retcode = retcode
        self.stdout = stdout
        self.stderr = stderr

    def __str__(self):
        return 'CaptureException(retcode=%s, stdout=%r, stderr=%r)' % (
            self.retcode,
            self.stdout,
            self.stderr
        )


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


def exec_kubectl(config, cmd):
    pre = [config.get('kubectl_path', 'kubectl')]

    namespace_exists = any([x.startswith('--namespace') for x in cmd])
    if 'namespace' in config and '-n' not in cmd and not namespace_exists:
        pre.extend(['-n', config['namespace']])

    logger.debug('Command: %r', pre + cmd)

    p = subprocess.Popen(pre + cmd, env=get_environment(config))
    ret = p.wait()

    if ret != 0:
        print('-----', file=sys.stderr)
        print('kubectl returned an error (%d), command args were:' % ret, file=sys.stderr)
        print(repr(pre + cmd), file=sys.stderr)

    return ret


def capture_kubectl(config, cmd):
    pre = [config.get('kubectl_path', 'kubectl')]

    namespace_exists = any([x.startswith('--namespace') for x in cmd])
    if 'namespace' in config and '-n' not in cmd and not namespace_exists:
        pre.extend(['-n', config['namespace']])

    logger.debug('Capturing command: %r', pre + cmd)

    p = subprocess.Popen(pre + cmd,
                         env=get_environment(config),
                         stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)
    out, err = p.communicate()
    if p.returncode != 0:
        raise CaptureException(p.returncode, out, err)

    return out, err


def get_current_master(config):
    context, _ = capture_kubectl(config, ['config', 'current-context'])
    cluster_name = context.strip().split('@')[1]
    logger.debug('Found current cluster name: %s' % cluster_name)

    path = '{.clusters[?(@.name=="%s")].cluster.server}' % cluster_name
    server, _ = capture_kubectl(config, ['config', 'view', '-o=jsonpath=%s' % path])
    server = server.strip()
    if not server:
        raise Exception('Could not determine kubernetes master host!')

    logger.debug('Kubernetes master node is: %s' % server)
    parsed = urlparse.urlparse(server)

    return parsed.hostname


def is_pod_name(config, arg):
    try:
        capture_kubectl(config, ['get', 'pod', arg])
        return True
    except CaptureException:
        return False


def select_resource(config, selectors, resource_type='pod', extra_args=None):
    if extra_args is None:
        extra_args = []

    if len(selectors) == 1 and is_pod_name(config, selectors[0]):
        return [selectors[0]]

    # if the user specifies an index, return only that
    index = None
    filtered_selectors = []
    for selector in selectors:
        try:
            index = int(selector)
        except ValueError:
            filtered_selectors.append(selector)

    cmd = ['get', resource_type,
           '-l', ','.join(filtered_selectors),
           '-o=jsonpath={.items[*].metadata.name}']

    ret, _ = capture_kubectl(config, cmd + extra_args)
    results = ret.strip().split()

    if index is None:
        return results
    else:
        return [results[index]]


@verb('select',
      aliases=['sel', 's'],
      description='Find an exact resource name based on labels')
def handle_select(config, remaining_args):
    parser = ArgumentParser(prog='kc select',
                            description='Finds an exact resource '
                                        'name based on labels')
    parser.add_argument('--resource', '-r', default='pod',
                        help='The resource type (default: pod)')
    parser.add_argument('--namespace', '-n', help='Provide or override a namespace')
    parser.add_argument('selectors', nargs='+',
                        help='One or more key=value selectors, space-separated')
    args = parser.parse_args(remaining_args)

    config = config.copy()
    if args.namespace:
        config['namespace'] = args.namespace

    for match in select_resource(config, args.selectors, args.resource):
        print(match)

    return True


@verb('nodeport', aliases=['np', 'port'], description='Resolve a service nodeport')
def handle_nodeport(config, remaining_args):
    parser = ArgumentParser(prog='kc nodeport',
                            description='Resolves a service nodeport')
    parser.add_argument('service_name',
                        help='The name of the service to query.')
    parser.add_argument('port', nargs='?', default='0',
                        help='The port name or index (default: 0)')
    parser.add_argument('remainder', nargs=REMAINDER,
                        help='Other args to pass to kubectl')
    args = parser.parse_args(remaining_args)

    cmd = ['get', 'service', args.service_name]
    try:
        port = int(args.port)
        cmd.append('-o=jsonpath={.spec.ports[%d].nodePort}' % port)
    except ValueError:
        cmd.append('-o=jsonpath={.spec.ports[?(@.name=="%s")].nodePort}' % args.port)

    ret, _ = capture_kubectl(config, cmd + args.remainder)
    print(ret.strip())

    return True


@verb('browse', aliases=['br', 'b'], description='Open the system browser to a service')
def browse(config, remaining_args):
    parser = ArgumentParser(prog='kc browse',
                            description='Opens the system browser to a service')
    parser.add_argument('--namespace', '-n', help='Provide or override a namespace')
    parser.add_argument('--protocol', '-p', default='http',
                        help='The URL protocol to open')
    parser.add_argument('service_name',
                        help='The name of the service to query.')
    parser.add_argument('port', nargs='?', default='0',
                        help='The port name or index (default: 0)')
    args = parser.parse_args(remaining_args)

    config = config.copy()
    if args.namespace:
        config['namespace'] = args.namespace

    cmd = ['get', 'service', args.service_name]
    try:
        port = int(args.port)
        cmd.append('-o=jsonpath={.spec.ports[%d].nodePort}' % port)
    except ValueError:
        cmd.append('-o=jsonpath={.spec.ports[?(@.name=="%s")].nodePort}' % args.port)

    host = get_current_master(config)
    port, _ = capture_kubectl(config, cmd)
    logger.debug('NodePort for service is: %s' % port)

    webbrowser.open('%s://%s:%s/' % (args.protocol, host, port))

    return True


@verb('bash', description='Open a bash shell in a pod by selector')
def handle_bash(config, remaining_args):
    parser = ArgumentParser(prog='kc bash',
                            description='Open a bash shell in a pod by selector')
    parser.add_argument('--namespace', '-n',
                        help='Provide or override a namespace')
    parser.add_argument('--container', '-c', default=None,
                        help='Execute in a particular container (if n>0 in pod)')
    parser.add_argument('selectors', nargs='+',
                        help='One or more key=value selectors (see `kc select`)')
    args = parser.parse_args(remaining_args)

    config = config.copy()
    if args.namespace:
        config['namespace'] = args.namespace

    matches = select_resource(config, args.selectors, 'pod')
    if not matches:
        print('No matches found for selector.')
        return False
    if len(matches) > 1:
        print('Selector matches multiple pods. Either refine it or '
              'provide an index.', file=sys.stderr)
        for i, match in enumerate(matches):
            print(' %3d %s' % (i, match), file=sys.stderr)
        return False

    cmd = ['exec', '-it', matches[0]]
    if args.container:
        cmd.extend(['-c', args.container])
    cmd.append('bash')

    return exec_kubectl(config, cmd)


@verb('sh', description='Open a \'sh\' shell in a pod by selector')
def handle_sh(config, remaining_args):
    parser = ArgumentParser(prog='kc bash',
                            description='Open a \'sh\' shell in a pod by selector')
    parser.add_argument('--namespace', '-n',
                        help='Provide or override a namespace')
    parser.add_argument('--container', '-c', default=None,
                        help='Execute in a particular container (if n>0 in pod)')
    parser.add_argument('selectors', nargs='+',
                        help='One or more key=value selectors (see `kc select`)')
    args = parser.parse_args(remaining_args)

    config = config.copy()
    if args.namespace:
        config['namespace'] = args.namespace

    matches = select_resource(config, args.selectors, 'pod')
    if not matches:
        print('No matches found for selector.')
        return False
    if len(matches) > 1:
        print('Selector matches multiple pods. Either refine it or '
              'provide an index.', file=sys.stderr)
        for i, match in enumerate(matches):
            print(' %3d %s' % (i, match), file=sys.stderr)
        return False

    cmd = ['exec', '-it', matches[0]]
    if args.container:
        cmd.extend(['-c', args.container])
    cmd.append('sh')

    return exec_kubectl(config, cmd)


def handle_special(config, name, remaining_args):
    verb_defs = filter(lambda v: name == v['name'] or name in v['aliases'], verbs)
    if verb_defs:
        return verb_defs[0]['function'](config, remaining_args)
    else:
        return None


def print_kc_help():
    print('-----')
    print('kc wraps kubectl to provide extra functionality.')
    print('')

    print('Additional Commands:')
    for verb_def in verbs:
        if len(verb_def['aliases']) > 0:
            aka = ' (aka %s)' % ','.join(verb_def['aliases'])
        else:
            aka = ''

        print('  %-15s%s%s' % (verb_def['name'], verb_def['description'] or '', aka))


def main():
    if 'KC_DEBUG' in os.environ:
        logger.setLevel(logging.DEBUG)

    config = load_config()
    user_args = sys.argv[1:]

    if not user_args or user_args[0] in ('help', '--help', '-h'):
        exec_kubectl(config, user_args)
        print_kc_help()
        sys.exit(0)

    try:
        special_ret = handle_special(config, user_args[0], user_args[1:])
        if special_ret is None:
            sys.exit(exec_kubectl(config, user_args))
        elif isinstance(special_ret, bool):
            sys.exit(0 if special_ret is True else 1)
        else:
            sys.exit(special_ret)
    except CaptureException as ex:
        logger.debug('Error in command capture!', exc_info=ex)

        print(ex.stderr, file=sys.stderr, end='')
        sys.exit(ex.retcode)


if __name__ == '__main__':
    main()
