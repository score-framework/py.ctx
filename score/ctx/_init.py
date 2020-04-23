# Copyright © 2015-2018 STRG.AT GmbH, Vienna, Austria
# Copyright © 2019-2020 Necdet Can Ateşman, Vienna, Austria
#
# This file is part of the The SCORE Framework.
#
# The SCORE Framework and all its parts are free software: you can redistribute
# them and/or modify them under the terms of the GNU Lesser General Public
# License version 3 as published by the Free Software Foundation which is in
# the file named COPYING.LESSER.txt.
#
# The SCORE Framework and all its parts are distributed without any WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
# PARTICULAR PURPOSE. For more details see the GNU Lesser General Public
# License.
#
# If you have not received a copy of the GNU Lesser General Public License see
# http://www.gnu.org/licenses/.
#
# The License-Agreement realised between you as Licensee and STRG.AT GmbH as
# Licenser including the issue of its valid conclusion and its pre- and
# post-contractual effects is governed by the laws of Austria. Any disputes
# concerning this License-Agreement including the issue of its valid conclusion
# and its pre- and post-contractual effects are exclusively decided by the
# competent court, in whose district STRG.AT GmbH has its registered seat, at
# the discretion of STRG.AT GmbH also the competent court, in whose district
# the Licensee has his registered seat, an establishment or assets.

from collections import OrderedDict
import enum
from weakref import WeakKeyDictionary

from transaction import TransactionManager
from transaction.interfaces import IDataManager, ISynchronizer
from zope.interface import implementer

from score.init import ConfiguredModule


DEFAULTS = {
    'member.meta': 'meta',
    'member.tx': 'tx',
}


def init(confdict={}):
    """
    Initializes this module acoording to :ref:`our module initialization
    guidelines <module_initialization>`.
    """
    conf = DEFAULTS.copy()
    conf.update(confdict)
    meta_member = conf['member.meta']
    if meta_member and meta_member.strip().lower() == 'none':
        meta_member = None
    tx_member = conf['member.tx']
    if tx_member and tx_member.strip().lower() == 'none':
        tx_member = None
    return ConfiguredCtxModule(meta_member, tx_member)


class CtxMemberRegistration:

    def __init__(self,
                 name,
                 constructor,
                 setter,
                 destructor,
                 autojoin,
                 commit):
        self.name = name
        self.constructor = constructor
        self.setter = setter
        self.destructor = destructor
        self.autojoin = autojoin
        self.commit = commit


class DeadContextException(Exception):

    def __init__(self, ctx):
        self.ctx = ctx
        super().__init__('Trying to access attribute of a destroyed Context')


class ConfiguredCtxModule(ConfiguredModule):
    """
    This module's :class:`configuration class
    <score.init.ConfiguredModule>`. It acts as a factory for :class:`.Context`
    objects and provides an API for registering members on new Context objects,
    as well as hooks for context construction and destruction events.
    """

    def __init__(self, meta_member, tx_member):
        super().__init__('score.ctx')
        self.registrations = OrderedDict()
        self._create_callbacks = []
        self._destroy_callbacks = []
        self._meta_objects = WeakKeyDictionary()
        self.meta_member = meta_member
        self.tx_member = tx_member
        if meta_member:
            self.register(meta_member, self.get_meta)
        if tx_member:
            self.register(tx_member, self.get_tx)

    def _finalize(self, score):
        self.registrations['score'] = CtxMemberRegistration(
            'score', lambda ctx: score, None, None, None, None)
        members = {'_conf': self}
        for name, registration in self.registrations.items():
            members[name] = self._create_member(name, registration)
        self.Context = type('ConfiguredContext', (Context,), members)

    def get_meta(self, ctx, *, autocreate=True):
        if ctx not in self._meta_objects:
            if not isinstance(ctx, self.Context):
                raise ValueError('Context is not managed by this %s', (
                    self.__class__.__name__))
            if not autocreate:
                return None
            self._meta_objects[ctx] = ContextMetadata(ctx)
        return self._meta_objects[ctx]

    def get_tx(self, ctx):
        return self.get_meta(ctx).tx

    def register(self,
                 name,
                 constructor,
                 *,
                 setter=None,
                 destructor=None,
                 commit=None,
                 autojoin=None):
        """
        Registers a new :term:`member <context member>` on Context objects.
        This is the function to use when populating future Context objects. An
        example for fetching the current user from the session:

        >>> def constructor(ctx):
        ...     if not ctx.user_id:
        ...         return None
        ...     return ctx.db.query(User).filter(ctx.user_id).first()
        ...
        >>> ctx_conf.register('user', constructor)
        >>> with ctx_conf.Context() as ctx:
        ...     print(ctx.user.age())
        ...
        25

        The only required parameter *constructor* is a callable, that will be
        invoked the first time the attribute is accessed on a new Context.

        If the object created by the constructor needs to be cleaned up at the
        end of the context lifetime, it possible to do so in a separate
        *destructor*. That callable will receive three parameters:

        - The Context object,
        - whatever the constructor had returned, and
        - an exception, that was caught during the lifetime of the context.
          This last value is `None`, if the Context was destroyed without
          exception.
        """
        if self._finalized:
            raise Exception(
                'Cannot register member: configuration already finalized')
        if name == 'destroy' or not name or name[0] == '_':
            raise ValueError('Invalid name "%s"' % name)
        if name in self.registrations:
            raise ValueError('Member "%s" already registered' % (name,))
        if not setter and (autojoin or commit):
            setter = True
        self.registrations[name] = CtxMemberRegistration(
            name, constructor, setter, destructor, autojoin, commit)

    def on_create(self, callable):
        """
        Registers provided *callable* to be called whenever a new
        :class:`.Context` object is created. The callback will receive the
        newly created Context object as its sole argument.
        """
        if self._finalized:
            raise Exception(
                'Cannot add create listener: configuration already finalized')
        self._create_callbacks.append(callable)

    def on_destroy(self, callable):
        """
        Registers provided *callable* to be called whenever a :class:`.Context`
        object is destroyed. The callback will receive two arguments:

        - The Context object, which is about to be destroyed, and
        - an optional exception, which was thrown before the Context was
          gracefully destroyed.
        """
        if self._finalized:
            raise Exception(
                'Cannot add destroy listener: configuration already finalized')
        self._destroy_callbacks.append(callable)

    def _create_member(self, name, registration):
        getter = self._create_member_getter(name, registration)
        setter = self._create_member_setter(name, registration, getter)
        return property(getter, setter)

    def _create_member_getter(self, name, registration):
        def getter(ctx):
            meta = self.get_meta(ctx)
            if meta.dead:
                raise DeadContextException(ctx)
            if name not in meta.constructed_members:
                if not meta.active:
                    raise DeadContextException(ctx)
                value = registration.constructor(ctx)
                self.log.debug('Created member %s', name)
                meta.constructed_members[name] = value
                meta.persisted_values[name] = value
            return meta.constructed_members[name]
        getter.__name__ = 'get_ctx_' + name
        return getter

    def _create_member_setter(self, name, registration, getter):
        if not registration.setter:
            return None

        def setter(ctx, value):
            meta = self.get_meta(ctx)
            if meta.dead:
                raise DeadContextException(ctx)
            if name in meta.constructed_members:
                previous_value = meta.constructed_members[name]
            elif not meta.active:
                raise DeadContextException(ctx)
            else:
                previous_value = getter(ctx)
            if callable(registration.setter):
                registration.setter(ctx, previous_value, value)
            self.log.debug('Setting member %s', name)
            meta.constructed_members[name] = value
        setter.__name__ = 'set_ctx_' + name
        return setter


class Context:
    """
    Base class for Contexts of a ConfiguredCtxModule. Do not use this class
    directly, use the :attr:`Context <.ConfiguredCtxModule.Context>` member of
    a ConfiguredCtxModule instead.

    Every Context object needs to be destroyed manually by calling its
    :meth:`.destroy` method. Although this method will be called in the
    destructor of this class, that might already be too late. This is the
    reason why the preferred way of using this class is as a
    :term:`context manager <python:context manager>`:

    >>> with ctx_conf.Context() as ctx:
    ...     ctx.logout_user()
    ...
    """

    def __init__(self):
        if not hasattr(self, '_conf'):
            raise Exception('Unconfigured Context')
        self._conf.log.debug('Initializing')
        for callback in self._conf._create_callbacks:
            callback(self)

    def __del__(self):
        meta = self._conf.get_meta(self, autocreate=False)
        if meta and meta.active:
            self.destroy()

    def __enter__(self):
        meta = self._conf.get_meta(self)
        if not meta.active:
            raise DeadContextException(self)
        return self

    def __exit__(self, type, value, traceback):
        self.destroy(value)

    def destroy(self, exception=None):
        """
        Cleans up this context and makes it unusable.

        After calling this function, this object will lose all its magic and
        behave like an empty class.

        The optional *exception*, that is the cause of this method call, will
        be passed to the destructors of every :term:`context member`.
        """
        meta = self._conf.get_meta(self, autocreate=False)
        if not meta or not meta.active:
            return
        if exception:
            self._conf.log.debug('Destroying, %s: %s',
                                 type(exception).__name__, exception)
        else:
            self._conf.log.debug('Destroying')
        if self._conf.tx_member:
            transaction = self._conf.get_tx(self).get()
            if exception or transaction.isDoomed():
                transaction.abort()
            else:
                transaction.commit()
        meta.state = meta.State.DESTROYING
        for attr in reversed(list(meta.constructed_members.keys())):
            self._conf.log.debug('Deleting member %s', attr)
            destructor = self._conf.registrations[attr].destructor
            if destructor:
                self._conf.log.debug('Calling destructor of %s', attr)
                constructor_value = meta.constructed_members[attr]
                destructor(self, constructor_value, None)
            meta.constructed_members.pop(attr)
        for callback in self._conf._destroy_callbacks:
            callback(self, exception)
        if self._conf.tx_member:
            transaction = self._conf.get_tx(self).get()
            if exception or transaction.isDoomed():
                transaction.abort()
            else:
                transaction.commit()
        meta.state = meta.State.DEAD


@implementer(IDataManager)
class AutoCommitter:

    def __init__(self, meta, member_name, commit_callback, sort_key):
        self.meta = meta
        self.member_name = member_name
        self.commit_callback = commit_callback
        self.sort_key = sort_key
        self.abort_callback = None
        self.ctx = meta.ctx
        self.transaction_manager = meta.tx

    def tpc_finish(self, transaction):
        pass

    def sortKey(self):
        # This is an ad-hoc committer, it will probably modify another
        # IDataManager and should thus sort before anything using its name as
        # sort string. Ascii reminder:
        #
        #   ord('0') < ord('@') < ord('A') < ord('a')
        #
        return '@score.ctx.autocommit(%d)' % (self.sort_key,)

    def tpc_abort(self, transaction):
        if callable(self.abort_callback):
            self.abort_callback()
            self.abort_callback = None

    def abort(self, transaction):
        pass

    def tpc_begin(self, transaction):
        pass

    def commit(self, transaction):
        old = self.meta.persisted_values[self.member_name]
        new = self.meta.constructed_members[self.member_name]
        self.abort_callback = self.commit_callback(self.ctx, old, new)

    def tpc_vote(self, transaction):
        pass


@implementer(ISynchronizer)
class TransactionSynchronizer:

    def __init__(self, meta):
        self.meta = meta
        self.ctx = meta.ctx
        self.conf = meta.conf

    def newTransaction(self, transaction):
        pass

    def beforeCompletion(self, transaction):
        sort_key = len(self.meta.constructed_members)
        for name, current_value in self.meta.constructed_members.items():
            registration = self.conf.registrations[name]
            if not registration.autojoin and not registration.commit:
                continue
            persisted_value = self.meta.persisted_values[name]
            # if persisted_value == current_value:
            #     continue
            if registration.autojoin:
                transaction.join(registration.autojoin(
                    self.ctx, persisted_value, current_value))
            if registration.commit:
                sort_key -= 1
                transaction.join(AutoCommitter(
                    self.meta, name, registration.commit, sort_key))

    def afterCompletion(self, transaction):
        pass


class ContextMetadata:

    _tx = None

    _tx_synchronizer = None

    _registered_members = None

    @enum.unique
    class State(enum.IntEnum):
        DEAD = 0
        ACTIVE = 1
        DESTROYING = 2

    def __init__(self, ctx):
        self.ctx = ctx
        self.conf = ctx._conf
        self.state = self.State.ACTIVE
        self.destoying = False
        self.constructed_members = OrderedDict()
        self.persisted_values = {}

    @property
    def tx(self):
        if self._tx is None:
            self._tx = TransactionManager()
            self._tx_synchronizer = TransactionSynchronizer(self)
            self._tx.registerSynch(self._tx_synchronizer)
        return self._tx

    @property
    def active(self):
        return self.state == self.State.ACTIVE

    @property
    def destroying(self):
        return self.state == self.State.DESTROYING

    @property
    def dead(self):
        return self.state == self.State.DEAD

    @property
    def registered_members(self):
        if self._registered_members is None:
            self._registered_members = list(self.conf.registrations.keys())
        return self._registered_members

    def member_exists(self, name):
        return name in self.registered_members

    def member_constructed(self, name):
        return name in self.constructed_members
