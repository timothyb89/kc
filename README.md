kc - make kubectl less annoying
===============================

A small wrapper for `kubectl` that make some some functionality a bit
friendlier.

 * Automatically set namespace, cluster configuration, and environment variables
   for a directory tree
 * TODO: shorten some common commands

Install
-------

    git clone https://github.com/timothyb89/kc.git
    sudo pip install -r kc/requirements.txt
    ln -s `pwd`/kc/kc.py ~/bin/kc

You can update by running `git pull` in the checked out `kc` directory.

Usage
-----

### Directory configuration

Add a `.kc.yml` in your project directory containing something like the
following:

```yaml
namespace: my-namespace
env:
  NO_PROXY: kube1,kube2,kube3,kube4
  KUBECONFIG: /home/my_user/admin.conf
```

Everything shown above is optional. If `KUBECONFIG` is set under `env`, it will
override the default file (usually `~/.kube/config`). If `namespace` is set, it
automatically appends `-n <namespace>`.

Then, instead of running `kubectl`, run `kc`. The actual parameters you enter
are passed to `kubectl`, but will be adjusted based on values in `.kc.yml`.

Examples:
 * `kubectl get pods -n my-namespace` becomes `kc get pods`
 * `kubectl --kubeconfig /path/to/some/config.conf ...` becomes `kc ...`

By default the environment for all `kubectl` commands is inherited. If desired,
this can be disabled by setting `inherit: false` in `.kc.yml`.

### Environment configuration

Most options can also be configured using environment variables. If a `.kc.yml`
exists, settings configured in environment variables will override any in the
config file.

 * `KC_NAMESPACE`: if set, automatically appends `-n $KC_NAMESPACE` to all
   generated `kubectl` commands

Some common environment variables can also be overridden. If set, these will
override any values configured in `.kc.yml`, or if `inherit: false` is set, will
be passed to the `kubectl` child process:

 * `KC_KUBECONFIG`
 * `KC_HTTP_PROXY`
 * `KC_HTTPS_PROXY`
 * `KC_NO_PROXY`

### Helper commands

In addition to wrapping all standard `kubectl` commands, `kc` also provides a
few extra subcommands that make common operations a bit easier:

 * `kc select` (aka `kc sel`, `kc s`): returns a space-separated list of full
   resource names given a set of labels. For example:
   
       $ kc select app=grafana
       grafana-1548781338-gjlps

   This can be used to easily run commands on resources whose names may change,
   for example:
   
       $ kc logs -f $(kc select app=grafana)
       $ kc exec -it $(kc select app=grafana) bash

   Note that by default the resource is `pod` but that can be overridden with
   `-r <type>`. See also: `kc select --help`.

 * `kc nodeport` (aka `kc np`): returns a plain integer port for a service
   NodePort, useful for finding where a randomly-allocated port can be accessed.
   Example:
   
       $ kc nodeport grafana
       31577

   If multiple ports are exposed, the first is returned. This can be overridden
   by specifying an integer index (e.g. `kc nodeport grafana 1`) or a port name
   (e.g. `kc nodeport grafana http`).

A full list of supported sub-commands is available when running `kc help` (it
will be printed at the bottom of the existing `kubectl` help message).
