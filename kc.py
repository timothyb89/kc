#!/usr/bin/env python

import argparse
import logging
import os
import subprocess
import sys

import yaml


logging.basicConfig(level=logging.WARN)
logger = logging.getLogger(__name__)


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


def prepare_command(config, user_args):
    cmd_path = config.get('kubectl_path', 'kubectl')
    args = [cmd_path]
    env = config['env']

    if 'namespace' in config:
        args.extend(['-n', config['namespace']])

    args.extend(user_args)

    return args, env


def main():
    if 'KC_DEBUG' in os.environ:
        logger.setLevel(logging.DEBUG)

    config = load_config()
    args, env = prepare_command(config, sys.argv[1:])

    if config.get('inherit_env', True) is True:
        env_ = os.environ.copy()
        env_.update(env)
        env = env_

    p = subprocess.Popen(args, env=env)
    p.wait()


if __name__ == '__main__':
    main()
