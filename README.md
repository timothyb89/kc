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
Add a `.kc.yml` containing something like the following:

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
