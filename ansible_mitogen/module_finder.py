# Copyright 2017, David Wilson
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
# this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its contributors
# may be used to endorse or promote products derived from this software without
# specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

from __future__ import absolute_import
import collections
import imp
import os

import mitogen.master


PREFIX = 'ansible.module_utils.'


Module = collections.namedtuple('Module', 'name path kind parent')


def get_fullname(module):
    """
    Reconstruct a Module's canonical path by recursing through its parents.
    """
    bits = [str(module.name)]
    while module.parent:
        bits.append(str(module.parent.name))
        module = module.parent
    return '.'.join(reversed(bits))


def get_code(module):
    """
    Compile and return a Module's code object.
    """
    fp = open(module.path)
    try:
        return compile(fp.read(), str(module.name), 'exec')
    finally:
        fp.close()


def is_pkg(module):
    """
    Return :data:`True` if a Module represents a package.
    """
    return module.kind == imp.PKG_DIRECTORY


def find(name, path=(), parent=None):
    """
    Return a Module instance describing the first matching module found on the
    given search path.

    :param str name:
        Module name.
    :param str path:
        Search path.
    :param Module parent:
        If given, make the found module a child of this module.
    """
    head, _, tail = name.partition('.')
    try:
        tup = imp.find_module(head, list(path))
    except ImportError:
        return parent

    fp, path, (suffix, mode, kind) = tup
    if fp:
        fp.close()

    if kind == imp.PKG_DIRECTORY:
        path = os.path.join(path, '__init__.py')
    module = Module(head, path, kind, parent)
    if tail:
        return find_relative(module, tail, path)
    return module


def find_relative(parent, name, path=()):
    path = [os.path.dirname(parent.path)] + list(path)
    return find(name, path, parent=parent)


def scan_fromlist(code):
    for level, modname_s, fromlist in mitogen.master.scan_code_imports(code):
        for name in fromlist:
            yield level, '%s.%s' % (modname_s, name)
        if not fromlist:
            yield level, modname_s


def scan(module_name, module_path, search_path):
    module = Module(module_name, module_path, imp.PY_SOURCE, None)
    stack = [module]
    seen = set()

    while stack:
        module = stack.pop(0)
        for level, fromname in scan_fromlist(get_code(module)):
            if not fromname.startswith(PREFIX):
                continue

            imported = find(fromname[len(PREFIX):], search_path)
            if imported is None or imported in seen:
                continue

            seen.add(imported)
            stack.append(imported)
            parent = imported.parent
            while parent:
                fullname = get_fullname(parent)
                module = Module(fullname, parent.path, parent.kind, None)
                if module not in seen:
                    seen.add(module)
                    stack.append(module)
                parent = parent.parent

    return sorted(
        (PREFIX + get_fullname(module), module.path, is_pkg(module))
        for module in seen
    )
