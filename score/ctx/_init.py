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

from transaction import TransactionManager
from transaction.interfaces import IDataManager
from zope.interface import implementer

from score.init import ConfiguredModule


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

    def __init__(self, name, constructor, destructor):
        self.name = name
        self.constructor = constructor
        self.destructor = destructor


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
        self._meta_objects = {}
        self.register('ctx_meta', self.get_meta)

    def _finalize(self, score):
        self.registrations['score'] = CtxMemberRegistration(
            'score', lambda ctx: score, None)
        members = {'_conf': self}
        for name, registration in self.registrations.items():
            members[name] = self._create_member(name, registration)
        self._destroy_callbacks.append(self._delete_meta)
        self.Context = type('ConfiguredContext', (Context,), members)

    def _delete_meta(self, ctx, _exception):
        self._meta_objects.pop(self, None)

    def get_meta(self, ctx, *, autocreate=True):
        if ctx not in self._meta_objects:
            if not isinstance(ctx, self.Context):
                raise ValueError('Given Context is not managed by this %s', (
                    self.__class__.__name__))
            if not autocreate:
                return None
            self._meta_objects[ctx] = ContextMetadata(ctx)
        return self._meta_objects[ctx]

    def register(self, name, constructor, destructor=None):
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
        if name == 'destroy' or not name or name[0] == '_':
            raise ValueError('Invalid name "%s"' % name)
        if name in self.registrations:
            raise ValueError('Member "%s" already registered' % (name,))
        self.registrations[name] = CtxMemberRegistration(
            name, constructor, destructor)

    def on_create(self, callable):
        """
        Registers provided *callable* to be called whenever a new
        :class:`.Context` object is created. The callback will receive the
        newly created Context object as its sole argument.
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

    def _create_member(self, name, registration):

        def getter(ctx):
            meta = self.get_meta(ctx)
            if name in meta.assigned_members[name]:
                return meta.assigned_members[name]
            if name in meta.constructed_members:
                value = meta.constructed_members[name]
                meta.assigned_members[name] = value
                return value
            value = registration.constructor()
            meta.constructed_members[name] = value
            meta.assigned_members[name] = value
            return value
        getter.__name__ = 'get_ctx_' + name

        def setter(ctx, value):
            meta = self.get_meta(ctx)
            if name not in meta.constructed_members:
                initial_value = registration.constructor()
                meta.constructed_members[name] = initial_value
            meta.assigned_members[name] = value
        setter.__name__ = 'set_ctx_' + name

        def deller(ctx):
            meta = self.get_meta(ctx)
            meta.assigned_members.pop(name)
        deller.__name__ = 'del_ctx_' + name

        return property(getter, setter, deller)


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
        self._conf.log.debug('Initializing')
        self.tx_manager = TransactionManager()
        for callback in self._conf._create_callbacks:
            callback(self)

    def __del__(self):
        meta = self._conf.get_meta(self, autocreate=False)
        if meta and meta.active:
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
        meta = self._conf.get_meta(self, autocreate=False)
        if not meta or not meta.active:
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
        meta.active = False
        for attr in reversed(list(meta.constructed_members.keys())):
            constructor_value = meta.constructed_members.pop(attr)
            self._conf.log.debug('Deleting member %s' % attr)
            destructor = self._conf.registrations[attr].destructor
            if destructor:
                self._conf.log.debug('Calling destructor of %s' % attr)
                destructor(self, constructor_value, exception)
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
