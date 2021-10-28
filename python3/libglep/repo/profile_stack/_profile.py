import os
from snakeoil import klass
from snakeoil.osutils import abspath, pjoin
from snakeoil.bash import iter_read_bash, read_bash_dict
from ...core._pkg_wildcard import PkgWildcard
from ...errors import ProfileNotExistError
from ...errors import ProfileParseError
from ...errors import InvalidPkgWildcard


class Profile(metaclass=klass.immutable_instance):

    def __init__(self, repo, name, pms_strict=True):
        self._repo = repo
        self._name = name
        self._pms_strict = pms_strict

        if not os.path.isdir(self._profile_path()):
            raise ProfileNotExistError(self._profile_path())

    def __str__(self):
        return f"profile of %s at %s" % (self._repo, os.path.join("profiles", self._name))

    def __repr__(self):
        return '<%s repo=%r name=%r, @%#8x>' % (self.__class__.__name__, self._repo, self._name, id(self))

    def name(self):
        """Relative path to the profile from the profiles directory."""
        return self._name

    @klass.jit_attr
    def packages(self):
        # TODO: get profile-set support into PMS
        profile_set = 'profile-set' in self._repo.profile_formats
        relpath = self._property_file_path("packages")
        sys, neg_sys, pro, neg_pro, neg_wildcard = [], [], [], [], False
        for line, lineno in self._read_profile_property_file(relpath):
            try:
                if line[0] == '-':
                    if line == '-*':
                        neg_wildcard = True
                    elif line[1] == '*':
                        neg_sys.append(PkgWildcard(line[2:]))
                    elif profile_set:
                        neg_pro.append(PkgWildcard(line[1:]))
                    else:
                        raise ProfileParseError(relpath, "invalid line format", line=line, lineno=lineno)
                else:
                    if line[0] == '*':
                        sys.append(PkgWildcard(line[1:]))
                    elif profile_set:
                        pro.append(PkgWildcard(line))
                    else:
                        raise ProfileParseError(relpath, "invalid line format", line=line, lineno=lineno)
            except InvalidPkgWildcard as e:
                raise ProfileParseError(relpath, f"parsing error: {e}", line=line, lineno=lineno)
        system = [tuple(neg_sys), tuple(sys)]
        profile = [tuple(neg_pro), tuple(pro)]
        if neg_wildcard:
            system.append(neg_wildcard)
            profile.append(neg_wildcard)
        return ProfilePackages(tuple(system), tuple(profile))

    @klass.jit_attr
    def parent_paths(self):
        relpath = self._property_file_path()
        for line, lineno in self._parse_profile_property_file("parent"):
            if 'portage-2' in self._repo.profile_formats:
                repo_id, separator, profile_path = line.partition(':')
                if separator:
                    if profile_path.find("..") >= 0:
                        raise ProfileParseError(relpath, "invalid line format", line=line, lineno=lineno)
                    yield (line, repo_id)
                    continue
            yield (abspath(pjoin(self._profile_path(), line)), None)

    @klass.jit_attr
    def pkg_provided(self):
        relpath = self._property_file_path("package.provided")
        for line, lineno in self._read_profile_property_file(relpath, eapi_optional='profile_pkg_provided'):
            try:
                yield CPV(line)
            except errors.InvalidCPV:
                raise ProfileParseError(relpath, "invalid package.provided entry", line=line, lineno=lineno)

    @klass.jit_attr
    def masks(self):
        data = self._read_profile_property_file(self._property_file_path("package.mask"))
        return self._parse_atom_negations(data)

    @klass.jit_attr
    def unmasks(self):
        data = self._read_profile_property_file("package.unmask")
        return self._parse_atom_negations(data)

    @klass.jit_attr
    def pkg_deprecated(self):
        data = self._read_profile_property_file("package.deprecated")
        return self._parse_atom_negations(data)

    @klass.jit_attr
    def keywords(self):
        data = self._read_profile_property_file("package.keywords")
        return self._parse_atom_negations(data)

    @klass.jit_attr
    def accept_keywords(self):
        data = self._read_profile_property_file("package.accept_keywords")
        return self._parse_atom_negations(data)

    @klass.jit_attr
    def pkg_use(self):
        data = self._read_profile_property_file("package.use")
        c = ChunkedDataDict()
        c.update_from_stream(chain.from_iterable(self._parse_package_use(data).values()))
        c.freeze()
        return c

    @klass.jit_attr
    def deprecated(self):
        path = os.path.join(self.path, "deprecated")
        try:
            data = pathlib.Path(path).read_text()
            i = data.find("\n")
            if i < 0:
                raise ParseError(f"deprecated profile missing replacement: '{self.name}/deprecated'")
            if len(data) > i + 1 and data[i+1] != "\n":
                raise ParseError(f"deprecated profile missing message: '{self.name}/deprecated'")
            replacement = data[:i]          # replacement is in the line 1
            msg = data[i+2:]                # line 2 is empty, line 3 and the following is the message
            return (replacement, msg)
        except FileNotFoundError:
            return None

    @klass.jit_attr
    def use_force(self):
        data = self._read_profile_property_file("use.force")
        return self._parse_use(data)

    @klass.jit_attr
    def use_stable_force(self):
        data = self._read_profile_property_file("use.stable.force", eapi_optional='profile_stable_use')
        return self._parse_use(data)

    @klass.jit_attr
    def pkg_use_force(self):
        data = self._read_profile_property_file("package.use.force")
        return self._parse_package_use(data)

    @klass.jit_attr
    def pkg_use_stable_force(self):
        data = self._read_profile_property_file("package.use.stable.force", eapi_optional='profile_stable_use')
        return self._parse_package_use(data)

    @klass.jit_attr
    def use_mask(self):
        data = self._read_profile_property_file("use.mask")
        return self._parse_use(data)

    @klass.jit_attr
    def use_stable_mask(self):
        data = self._read_profile_property_file("use.stable.mask", eapi_optional='profile_stable_use')
        return self._parse_use(data)

    @klass.jit_attr
    def pkg_use_mask(self):
        data = self._read_profile_property_file("package.use.mask")
        return self._parse_package_use(data)

    @klass.jit_attr
    def pkg_use_stable_mask(self):
        data = self._read_profile_property_file("package.use.stable.mask", eapi_optional='profile_stable_use')
        return self._parse_package_use(data)

    @klass.jit_attr
    def masked_use(self):
        c = self.use_mask
        if self.pkg_use_mask:
            c = c.clone(unfreeze=True)
            c.update_from_stream(chain.from_iterable(self.pkg_use_mask.values()))
            c.freeze()
        return c

    @klass.jit_attr
    def stable_masked_use(self):
        c = self.use_mask.clone(unfreeze=True)
        if self.use_stable_mask:
            c.merge(self.use_stable_mask)
        if self.pkg_use_mask:
            c.update_from_stream(chain.from_iterable(self.pkg_use_mask.values()))
        if self.pkg_use_stable_mask:
            c.update_from_stream(chain.from_iterable(self.pkg_use_stable_mask.values()))
        c.freeze()
        return c

    @klass.jit_attr
    def forced_use(self):
        c = self.use_force
        if self.pkg_use_force:
            c = c.clone(unfreeze=True)
            c.update_from_stream(chain.from_iterable(self.pkg_use_force.values()))
            c.freeze()
        return c

    @klass.jit_attr
    def stable_forced_use(self):
        c = self.use_force.clone(unfreeze=True)
        if self.use_stable_force:
            c.merge(self.use_stable_force)
        if self.pkg_use_force:
            c.update_from_stream(chain.from_iterable(self.pkg_use_force.values()))
        if self.pkg_use_stable_force:
            c.update_from_stream(chain.from_iterable(self.pkg_use_stable_force.values()))
        c.freeze()
        return c

    @klass.jit_attr
    def make_defaults(self):
        data = self._read_profile_property_file("make.defaults", fallback=None)
        d = {}
        if data is not None:
            d.update(read_bash_dict(data[0]))
        return ImmutableDict(d)

    @klass.jit_attr
    def default_env(self):
        data = self._read_profile_property_file("make.defaults", fallback=None)
        rendered = _make_incrementals_dict()
        for parent in self.parents:
            rendered.update(parent.default_env.items())

        if data is not None:
            data = read_bash_dict(data[0], vars_dict=rendered)
            rendered.update(data.items())
        return ImmutableDict(rendered)

    @klass.jit_attr
    def bashrc(self):
        path = pjoin(self.path, "profile.bashrc")
        if os.path.exists(path):
            return local_source(path)
        return None

    @klass.jit_attr
    def eapi(self):
        fullfn = os.path.join(self.path, "eapi")
        if not os.path.exists(fullfn):
            return "0"
        return pathlib.Path(fullfn).read_text().rstrip("\n")

    def _profile_path(self):
        return pjoin(self._repo.location, "profiles", self._name)

    def _property_file_path(self, filename):
        return pjoin(self._profile_path(), filename)

    def _read_profile_property_file(self, filename, eapi_optional=None, fallback=()):
        """
        :filename: str property file name
        :keyword fallback: What to return if the file does not exist for this profile. Must be immutable.
        :keyword eapi_optional: If given, the EAPI for this profile node is checked to see if
            the given optional evaluates to True; if so, then parsing occurs.  If False, then
            the fallback is returned and no ondisk activity occurs.
        """
        if eapi_optional is not None and not getattr(self.eapi.options, eapi_optional, None):
            data = fallback
        else:
            if not os.path.exists(filename):
                data = fallback
            else:
                data = iter_read_bash(filename, enum_line=True)
        for lineno, line in data:
            yield line, lineno

    def _parse_profile_property_file(self, filename, eapi_optional=None, fallback=(), parse_func=None):
        """
        :filename: str property file name
        :keyword fallback: What to return if the file does not exist for this profile. Must be immutable.
        :keyword eapi_optional: If given, the EAPI for this profile node is checked to see if
            the given optional evaluates to True; if so, then parsing occurs.  If False, then
            the fallback is returned and no ondisk activity occurs.
        """

        assert parse_func is not None
        filepath = self._property_file_path(filename)

        if eapi_optional is not None and not getattr(self.eapi.options, eapi_optional, None):
            data = fallback
        else:
            if not os.path.exists(filepath):
                data = fallback
            else:
                data = iter_read_bash(filepath, enum_line=True)
        for lineno, line in data:
            yield parse_func(line, lineno)

    def _parse_atom_negations(self, filepath):
        """Parse files containing optionally negated package atoms."""
        neg, pos = [], []
        for line, lineno, relpath in data:
            if line[0] == '-':
                line = line[1:]
                if not line:
                    logger.error(f"{relpath!r}, line {lineno}: '-' negation without an atom")
                    continue
                l = neg
            else:
                l = pos
            try:
                l.append(self.eapi_atom(line))
            except ebuild_errors.MalformedAtom as e:
                logger.error(f'{relpath!r}, line {lineno}: parsing error: {e}')
        return tuple(neg), tuple(pos)

    def _package_keywords_splitter(self, iterable):
        """Parse package keywords files."""
        for line, lineno, relpath in iterable:
            v = line.split()
            try:
                yield (atom(v[0]), tuple(stable_unique(v[1:])))
            except ebuild_errors.MalformedAtom as e:
                logger.error(f'{relpath!r}, line {lineno}: parsing error: {e}')

    def _parse_package_use(self):
        d = defaultdict(list)
        # split the data down ordered cat/pkg lines
        for line, lineno, relpath in data:
            l = line.split()
            try:
                a = self.eapi_atom(l[0])
            except ebuild_errors.MalformedAtom as e:
                logger.error(f'{relpath!r}, line {lineno}: parsing error: {e}')
                continue
            if len(l) == 1:
                logger.error(f'{relpath!r}, line {lineno}: missing USE flag(s): {line!r}')
                continue
            d[a.key].append(misc.chunked_data(a, *split_negations(l[1:])))

        return ImmutableDict((k, misc._build_cp_atom_payload(v, atom(k)))
                             for k, v in d.items())

    def _parse_use(self):
        c = misc.ChunkedDataDict()
        data = (x[0] for x in data)
        neg, pos = split_negations(data)
        if neg or pos:
            c.add_bare_global(neg, pos)
        c.freeze()
        return c


class ProfilePackages:

    def __init__(self, sys, pro):
        self.system = sys
        self.profiles = pro














class ProfileStack:

    def __init__(self, repo, name):
        self._repo = repo

        # current profile is the first element in self._profiles
        self._profiles = []
        self._add_profile_and_its_ancestors(name)
        self._profiles.reverse()

    def name(self):
        return self._profile[0]._name

    def packages(self):
        return self._profiles[0].packages

    @klass.jit_attr
    def pkg_provided(self):
        for p in self._profiles:
            for cpv in p.pkg_provided:
                yield cpv

    @klass.jit_attr
    def masks(self):
        data = self._read_profile_property_file("package.mask")
        return self._parse_atom_negations(data)

    @klass.jit_attr
    def unmasks(self):
        data = self._read_profile_property_file("package.unmask")
        return self._parse_atom_negations(data)

    @klass.jit_attr
    def pkg_deprecated(self):
        data = self._read_profile_property_file("package.deprecated")
        return self._parse_atom_negations(data)

    @klass.jit_attr
    def keywords(self):
        data = self._read_profile_property_file("package.keywords")
        return self._parse_atom_negations(data)

    @klass.jit_attr
    def accept_keywords(self):
        data = self._read_profile_property_file("package.accept_keywords")
        return self._parse_atom_negations(data)

    @klass.jit_attr
    def pkg_use(self):
        data = self._read_profile_property_file("package.use")
        c = ChunkedDataDict()
        c.update_from_stream(chain.from_iterable(self._parse_package_use(data).values()))
        c.freeze()
        return c

    @klass.jit_attr
    def deprecated(self):
        if self._profiles[0].deprecated:
            return True
        else:
            for p in self._profiles[1:]:
                if p.deprecated:
                    raise ParseError(f"parent profile {p.name} of profile {self.name} is deprecated")
            return False

    @klass.jit_attr
    def use_force(self):
        data = self._read_profile_property_file("use.force")
        return self._parse_use(data)

    @klass.jit_attr
    def use_stable_force(self):
        data = self._read_profile_property_file("use.stable.force", eapi_optional='profile_stable_use')
        return self._parse_use(data)

    @klass.jit_attr
    def pkg_use_force(self):
        data = self._read_profile_property_file("package.use.force")
        return self._parse_package_use(data)

    @klass.jit_attr
    def pkg_use_stable_force(self):
        data = self._read_profile_property_file("package.use.stable.force", eapi_optional='profile_stable_use')
        return self._parse_package_use(data)

    @klass.jit_attr
    def use_mask(self):
        data = self._read_profile_property_file("use.mask")
        return self._parse_use(data)

    @klass.jit_attr
    def use_stable_mask(self):
        data = self._read_profile_property_file("use.stable.mask", eapi_optional='profile_stable_use')
        return self._parse_use(data)

    @klass.jit_attr
    def pkg_use_mask(self):
        data = self._read_profile_property_file("package.use.mask")
        return self._parse_package_use(data)

    @klass.jit_attr
    def pkg_use_stable_mask(self):
        data = self._read_profile_property_file("package.use.stable.mask", eapi_optional='profile_stable_use')
        return self._parse_package_use(data)

    @klass.jit_attr
    def masked_use(self):
        c = self.use_mask
        if self.pkg_use_mask:
            c = c.clone(unfreeze=True)
            c.update_from_stream(chain.from_iterable(self.pkg_use_mask.values()))
            c.freeze()
        return c

    @klass.jit_attr
    def stable_masked_use(self):
        c = self.use_mask.clone(unfreeze=True)
        if self.use_stable_mask:
            c.merge(self.use_stable_mask)
        if self.pkg_use_mask:
            c.update_from_stream(chain.from_iterable(self.pkg_use_mask.values()))
        if self.pkg_use_stable_mask:
            c.update_from_stream(chain.from_iterable(self.pkg_use_stable_mask.values()))
        c.freeze()
        return c

    @klass.jit_attr
    def forced_use(self):
        c = self.use_force
        if self.pkg_use_force:
            c = c.clone(unfreeze=True)
            c.update_from_stream(chain.from_iterable(self.pkg_use_force.values()))
            c.freeze()
        return c

    @klass.jit_attr
    def stable_forced_use(self):
        c = self.use_force.clone(unfreeze=True)
        if self.use_stable_force:
            c.merge(self.use_stable_force)
        if self.pkg_use_force:
            c.update_from_stream(chain.from_iterable(self.pkg_use_force.values()))
        if self.pkg_use_stable_force:
            c.update_from_stream(chain.from_iterable(self.pkg_use_stable_force.values()))
        c.freeze()
        return c

    @klass.jit_attr
    def make_defaults(self):
        data = self._read_profile_property_file("make.defaults", fallback=None)
        d = {}
        if data is not None:
            d.update(read_bash_dict(data[0]))
        return ImmutableDict(d)

    @klass.jit_attr
    def default_env(self):
        data = self._read_profile_property_file("make.defaults", fallback=None)
        rendered = _make_incrementals_dict()
        for parent in self.parents:
            rendered.update(parent.default_env.items())

        if data is not None:
            data = read_bash_dict(data[0], vars_dict=rendered)
            rendered.update(data.items())
        return ImmutableDict(rendered)

    @klass.jit_attr
    def bashrc(self):
        return self._profiles[0].profile.bashrc

    @klass.jit_attr
    def eapi(self):
        fullfn = os.path.join(self.path, "eapi")
        if not os.path.exists(fullfn):
            return "0"
        return pathlib.Path(fullfn).read_text().rstrip("\n")






    def _add_profile_and_its_ancestors(self, name):
        pobj = Profile(self._repo, name)
        for p in pobj.parents:
            if p not in self._profiles:
                self._profiles.append(p)
        self._profiles.append(pobj)

    def _combine_all_profiles_property(self, property_name):
        








    deprecated = klass.alias_attr("node.deprecated")
    eapi = klass.alias_attr("node.eapi")
    name = klass.alias_attr("node.name")

    @klass.jit_attr
    def stack(self):
        def f(node):
            for path, line, lineno in node.parent_paths:
                try:
                    x = self.RawProfile._autodetect_and_create(path)
                except ProfileError as e:
                    repo_id = node.repoconfig.repo_id
                    logger.error(
                        f"repo {repo_id!r}: '{self.name}/parent' (line {lineno}), "
                        f'bad profile parent {line!r}: {e.error}'
                    )
                    continue
                for y in f(x):
                    yield y
            yield node
        return tuple(f(self.node))

    @klass.jit_attr
    def _system_profile(self):
        """User-selected system profile.

        This should map directly to the profile linked to /etc/portage/make.profile.
        """
        # prefer main system profile; otherwise, fallback to custom user profile
        for profile in reversed(self.stack):
            if not isinstance(profile, UserProfileNode):
                break
        return profile

    def _collapse_use_dict(self, attr):
        stack = (getattr(x, attr) for x in self.stack)
        d = misc.ChunkedDataDict()
        for mapping in stack:
            d.merge(mapping)
        d.freeze()
        return d

    @klass.jit_attr
    def forced_use(self):
        return self._collapse_use_dict("forced_use")

    @klass.jit_attr
    def masked_use(self):
        return self._collapse_use_dict("masked_use")

    @klass.jit_attr
    def stable_forced_use(self):
        return self._collapse_use_dict("stable_forced_use")

    @klass.jit_attr
    def stable_masked_use(self):
        return self._collapse_use_dict("stable_masked_use")

    @klass.jit_attr
    def pkg_use(self):
        return self._collapse_use_dict("pkg_use")

    def _collapse_generic(self, attr, clear=False):
        s = set()
        for node in self.stack:
            val = getattr(node, attr)
            if clear and len(val) > 2 and val[2]:
                s.clear()
            s.difference_update(val[0])
            s.update(val[1])
        return s

    @klass.jit_attr
    def default_env(self):
        d = dict(self.node.default_env.items())
        for incremental in const.incrementals:
            v = d.pop(incremental, '').split()
            if v:
                if incremental in const.incrementals_unfinalized:
                    d[incremental] = tuple(v)
                else:
                    v = misc.incremental_expansion(
                        v, msg_prefix=f"While expanding {incremental}, value {v!r}: ")
                    if v:
                        d[incremental] = tuple(v)
        return ImmutableDict(d.items())

    @property
    def profile_only_variables(self):
        if "PROFILE_ONLY_VARIABLES" in const.incrementals:
            return frozenset(self.default_env.get("PROFILE_ONLY_VARIABLES", ()))
        return frozenset(self.default_env.get("PROFILE_ONLY_VARIABLES", "").split())

    @klass.jit_attr
    def use_expand(self):
        """USE_EXPAND variables defined by the profile."""
        if "USE_EXPAND" in const.incrementals:
            return frozenset(self.default_env.get("USE_EXPAND", ()))
        return frozenset(self.default_env.get("USE_EXPAND", "").split())

    @klass.jit_attr
    def use(self):
        """USE flag settings for the profile."""
        return tuple(list(self.default_env.get('USE', ())) + list(self.expand_use()))

    def expand_use(self, env=None):
        """Expand USE_EXPAND settings to USE flags."""
        if env is None:
            env = self.default_env

        use = []
        for u in self.use_expand:
            value = env.get(u)
            if value is None:
                continue
            u2 = u.lower() + '_'
            use.extend(u2 + x for x in value.split())
        return tuple(use)

    @property
    def use_expand_hidden(self):
        if "USE_EXPAND_HIDDEN" in const.incrementals:
            return frozenset(self.default_env.get("USE_EXPAND_HIDDEN", ()))
        return frozenset(self.default_env.get("USE_EXPAND_HIDDEN", "").split())

    @property
    def iuse_implicit(self):
        if "IUSE_IMPLICIT" in const.incrementals:
            return frozenset(self.default_env.get("IUSE_IMPLICIT", ()))
        return frozenset(self.default_env.get("IUSE_IMPLICIT", "").split())

    @property
    def use_expand_implicit(self):
        if "USE_EXPAND_IMPLICIT" in const.incrementals:
            return frozenset(self.default_env.get("USE_EXPAND_IMPLICIT", ()))
        return frozenset(self.default_env.get("USE_EXPAND_IMPLICIT", "").split())

    @property
    def use_expand_unprefixed(self):
        if "USE_EXPAND_UNPREFIXED" in const.incrementals:
            return frozenset(self.default_env.get("USE_EXPAND_UNPREFIXED", ()))
        return frozenset(self.default_env.get("USE_EXPAND_UNPREFIXED", "").split())

    @klass.jit_attr
    def iuse_effective(self):
        iuse_effective = []

        # EAPI 5 and above allow profile defined IUSE injection (see PMS)
        if self._system_profile.eapi.options.profile_iuse_injection:
            iuse_effective.extend(self.iuse_implicit)
            for v in self.use_expand_implicit.intersection(self.use_expand_unprefixed):
                iuse_effective.extend(self.default_env.get("USE_EXPAND_VALUES_" + v, "").split())
            for v in self.use_expand.intersection(self.use_expand_implicit):
                for x in self.default_env.get("USE_EXPAND_VALUES_" + v, "").split():
                    iuse_effective.append(v.lower() + "_" + x)
        else:
            iuse_effective.extend(self._system_profile.repoconfig.known_arches)
            for v in self.use_expand:
                for x in self.default_env.get("USE_EXPAND_VALUES_" + v, "").split():
                    iuse_effective.append(v.lower() + "_" + x)

        return frozenset(iuse_effective)

    @klass.jit_attr
    def provides_repo(self):
        # delay importing to avoid circular imports
        from .repository import ProvidesRepo
        return ProvidesRepo(pkgs=self._collapse_generic("pkg_provided"))

    @klass.jit_attr
    def masks(self):
        return frozenset(chain(self._collapse_generic("masks")))

    @klass.jit_attr
    def unmasks(self):
        return frozenset(self._collapse_generic('unmasks'))

    @klass.jit_attr
    def pkg_deprecated(self):
        return frozenset(chain(self._collapse_generic("pkg_deprecated")))

    @klass.jit_attr
    def keywords(self):
        return tuple(chain.from_iterable(x.keywords for x in self.stack))

    @klass.jit_attr
    def accept_keywords(self):
        return tuple(chain.from_iterable(x.accept_keywords for x in self.stack))

    def _incremental_masks(self, stack_override=None):
        if stack_override is None:
            stack_override = self.stack
        return tuple(node.masks for node in stack_override if any(node.masks))

    def _incremental_unmasks(self, stack_override=None):
        if stack_override is None:
            stack_override = self.stack
        return tuple(node.unmasks for node in stack_override if any(node.unmasks))

    @klass.jit_attr
    def bashrcs(self):
        return tuple(x.bashrc for x in self.stack if x.bashrc is not None)

    bashrc = klass.alias_attr("bashrcs")
    path = klass.alias_attr("node.path")

    @klass.jit_attr
    def system(self):
        return frozenset(self._collapse_generic('system', clear=True))

    @klass.jit_attr
    def profile_set(self):
        return frozenset(self._collapse_generic('profile_set', clear=True))
