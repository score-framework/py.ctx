# Copyright © 2015-2018 STRG.AT GmbH, Vienna, Austria
# Copyright © 2019 Necdet Can Ateşman, Vienna, Austria
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
from score.init import ConfiguredModule
from transaction import TransactionManager
from transaction.interfaces import IDataManager
from zope.interface import implementer


def init(confdict={}):
    """
    Initializes this module acoording to :ref:`our module initialization
    guidelines <module_initialization>`.
    """
    conf = ConfiguredCtxModule()

    def constructor(ctx):
        tx = ctx.tx_manager.get()
        tx.join(_CtxDataManager(ctx))
        return tx

    conf.register('tx', constructor)
    return conf


@implementer(IDataManager)
class _CtxDataManager:
    """
    An :interface:`IDataManager <transaction.interfaces.IDataManager>`, which
    will remove the `tx' :term:`context member` once the transaction is
    committed or aborted.
    """

    def __init__(self, ctx):
        self.transaction_manager = ctx.tx_manager
        self.ctx = ctx

    def abort(self, transaction):
        del self.ctx.tx

    def tpc_begin(self, transaction):
        pass

    def commit(self, transaction):
        pass

    def tpc_vote(self, transaction):
        pass

    def tpc_finish(self, transaction):
        del self.ctx.tx

    def tpc_abort(self, transaction):
        del self.ctx.tx

    def sortKey(self):
        return 'score.ctx(%d)' % id(self)


class CtxMemberRegistration:

    def __init__(self, name, constructor, destructor, cached):
        self.name = name
        self.constructor = constructor
        self.destructor = destructor
        self.cached = cached


class ConfiguredCtxModule(ConfiguredModule):
    """
    This module's :class:`configuration class
    <score.init.ConfiguredModule>`. It acts as a factory for :class:`.Context`
    objects and provides an API for registering members on new Context objects,
    as well as hooks for context construction and destruction events.
    """

    def __init__(self):
        import score.ctx
        super().__init__(score.ctx)
        self.registrations = OrderedDict()
        self._create_callbacks = []
        self._destroy_callbacks = []

    def _finalize(self, score):
        self.registrations['score'] = CtxMemberRegistration(
            'score', lambda ctx: score, None)
        members = {'_conf': self}
        for name, registration in self.registrations.items():
            members[name] = _create_member(name, registration)
        self.Context = type('ConfiguredContext', (Context,), members)

    def register(self, name, constructor, destructor=None, cached=True):
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

        The value returned by the constructor will be *cached* in the Context
        object by default, i.e. the constructor will be called at most once for
        each Context. It is possible to add a context member, which will be
        called every time it is accessed by passing a `False` value as the
        *cached* parameter. Note that the destructor will only receive two
        parameters in this case (the context object and the optional
        exception).

        >>> from datetime import datetime
        >>> def constructor(ctx):
        ...     return datetime.now()
        ...
        >>> def destructor(ctx, exception):
        ...     pass
        ...
        >>> ctx_conf.register('now', constructor, destructor, cached=False)

        """
        if name == 'destroy' or not name or name[0] == '_':
            raise ValueError('Invalid name "%s"' % name)
        self.registrations[name] = CtxMemberRegistration(
            name, constructor, destructor, cached)

    def on_create(self, callable):
        """
        Registers provided *callable* to be called whenever a new
        :class:`.Context` object is created. The callback will receive the newly
        created Context object as its sole argument.
        """
        self._create_callbacks.append(callable)

    def on_destroy(self, callable):
        """
        Registers provided *callable* to be called whenever a :class:`.Context`
        object is destroyed. The callback will receive two arguments:

        - The Context object, which is about to be destroyed, and
        - an optional exception, which was thrown before the Context was
          gracefully destroyed.
        """
        self._destroy_callbacks.append(callable)


class Context:
    """
    Base class for Contexts of a ConfiguredCtxModule. Do not use this class
    directly, use the :attr:`Context <.ConfiguredCtxModule.Context>` member of
    a ConfiguredCtxModule instead.

    Every Context object needs to be destroyed manually by calling its
    :meth:`.destroy` method. Although this method will be called in the
    destructor of this class, that might already be too late. This is the
    reason why the preferred way of using this class is within a `with`
    statement:

    >>> with ctx_conf.Context() as ctx:
    ...     ctx.logout_user()
    ...
    """

    def __init__(self):
        if not hasattr(self, '_conf'):
            raise Exception('Unconfigured Context')
        self._meta = ContextMetadata(self)
        self._conf.log.debug('Initializing')
        self.tx_manager = TransactionManager()
        for callback in self._conf._create_callbacks:
            callback(self)

    def __del__(self):
        if self._meta.active:
            self.destroy()

    def __enter__(self):
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
        if not self._meta.active:
            return
        if exception:
            self._conf.log.debug('Destroying, %s: %s',
                                 type(exception).__name__, exception)
        else:
            self._conf.log.debug('Destroying')
        tx = self.tx_manager.get()
        if exception or tx.isDoomed():
            tx.abort()
        else:
            tx.commit()
        self._meta.active = False
        for attr in reversed(list(self._meta.constructed_members.keys())):
            constructor_value = self._meta.constructed_members.pop(attr)
            self._conf.log.debug('Deleting member %s' % attr)
            registration = self._conf.registrations[attr]
            destructor = registration.destructor
            if destructor:
                self._conf.log.debug('Calling destructor of %s' % attr)
                if registration.cached:
                    destructor(self, constructor_value, exception)
                else:
                    destructor(self, exception)
        for callback in self._conf._destroy_callbacks:
            callback(self, exception)


class ContextMetadata:

    _registered_members = None

    def __init__(self, ctx):
        self.ctx = ctx
        self.active = True
        self.constructed_members = {}
        self.assigned_members = {}

    @property
    def registered_members(self):
        if self._registered_members is None:
            self._registered_members = list(self.registrations.keys())
        return self._registered_members

    def member_exists(self, name):
        return name in self.registered_members

    def member_constructed(self, name):
        return name in self.constructed_members


def _create_member(name, registration):

    def getter(ctx):
        if name in ctx._meta.assigned_members[name]:
            return ctx._meta.assigned_members[name]
        if registration.cached and name in ctx._meta.constructed_members:
            value = ctx._meta.constructed_members[name]
            ctx._meta.assigned_members[name] = value
            return value
        value = registration.constructor()
        if registration.cached:
            ctx._meta.constructed_members[name] = value
        else:
            ctx._meta.constructed_members[name] = None
        ctx._meta.assigned_members[name] = value
        return value

    def setter(ctx, value):
        if name not in ctx._meta.constructed_members:
            initial_value = registration.constructor()
            ctx._meta.constructed_members[name] = initial_value
        ctx._meta.assigned_members[name] = value

    def deller(ctx):
        ctx._meta.assigned_members.pop(name)

    getter.__name__ = 'get_ctx_' + name
    setter.__name__ = 'set_ctx_' + name
    deller.__name__ = 'del_ctx_' + name
    return property(getter, setter, deller)
