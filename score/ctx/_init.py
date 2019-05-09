# Copyright © 2015-2018 STRG.AT GmbH, Vienna, Austria
#
# This file is part of the The SCORE Framework.
#
# The SCORE Framework and all its parts are free software: you can redistribute
# them and/or modify them under the terms of the GNU Lesser General Public
# License version 3 as published by the Free Software Foundation which is in the
# file named COPYING.LESSER.txt.
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
# the discretion of STRG.AT GmbH also the competent court, in whose district the
# Licensee has his registered seat, an establishment or assets.

from collections import namedtuple, OrderedDict
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


CtxMemberRegistration = namedtuple(
    'CtxMemberRegistration', 'constructor, destructor, cached')


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
        self.registrations = {}
        _conf = self

        class ConfiguredContext(Context):
            def __init__(self):
                self._conf = _conf
                super().__init__()
        self.Context = ConfiguredContext
        self._create_callbacks = []
        self._destroy_callbacks = []

    def _finalize(self, score):
        self.registrations['score'] = CtxMemberRegistration(
            lambda ctx: score, None, True)

    def register(self, name, constructor, destructor=None, cached=True):
        """
        Registers a new :term:`member <context member>` on Context objects. This
        is the function to use when populating future Context objects. An
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
        - an exception, that was caught during the lifetime of the context. This
          last value is `None`, if the Context was destroyed without exception.

        The value returned by the constructor will be *cached* in the Context
        object by default, i.e. the constructor will be called at most once for
        each Context. It is possible to add a context member, which will be
        called every time it is accessed by passing a `False` value as the
        *cached* parameter. Note that the destructor will only receive two
        parameters in this case (the context object and the optional exception).

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
            constructor, destructor, cached)

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
    directly, use the :attr:`Context <.ConfiguredCtxModule.Context>` member of a
    ConfiguredCtxModule instead.

    Every Context object needs to be destroyed manually by calling its
    :meth:`.destroy` method. Although this method will be called in the
    destructor of this class, that might already be too late. This is the reason
    why the preferred way of using this class is within a `with` statement:

    >>> with ctx_conf.Context() as ctx:
    ...     ctx.logout_user()
    ...
    """

    def __init__(self):
        if not hasattr(self, '_conf'):
            raise Exception('Unconfigured Context')
        self.log = self._conf.log
        self.log.debug('Initializing')
        self._constructed_attrs = OrderedDict()
        self._active = True
        self.tx_manager = TransactionManager()
        for callback in self._conf._create_callbacks:
            callback(self)

    def __del__(self):
        if self._active:
            self.destroy()

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.destroy(value)

    def __hasattr__(self, attr):
        if self._active:
            return attr in self._conf.registrations
        return attr in self.__dict__

    def __getattr__(self, attr):
        if '_active' in self.__dict__ and '_conf' in self.__dict__ and \
                self._active and attr in self._conf.registrations:
            value = self._conf.registrations[attr].constructor(self)
            if self._conf.registrations[attr].cached:
                self._constructed_attrs[attr] = value
                self.__dict__[attr] = value
            else:
                self._constructed_attrs[attr] = None
            self.log.debug('Creating member %s' % attr)
            return value
        raise AttributeError(attr)

    def __setattr__(self, attr, value):
        try:
            # call registered contructor, if there is one, so the destructor
            # gets called with this new value
            getattr(self, attr)
        except AttributeError:
            pass
        self.__dict__[attr] = value

    def __delattr__(self, attr):
        if attr in self._conf.registrations:
            if attr in self._constructed_attrs:
                self.__delattr(attr, None)
            elif attr in self.__dict__:
                del self.__dict__[attr]
        else:
            del self.__dict__[attr]

    def __delattr(self, attr, exception):
        """
        Deletes a previously constructed *attr*. Its destructor will receive the
        given *exception*.

        Note: this function assumes that the *attr* is indeed a registered
        context member. It will behave unexpectedly when called with an *attr*
        that has no registration.
        """
        constructor_value = self._constructed_attrs[attr]
        del self._constructed_attrs[attr]
        self.log.debug('Deleting member %s' % attr)
        destructor = self._conf.registrations[attr].destructor
        if destructor:
            self.log.debug('Calling destructor of %s' % attr)
            if self._conf.registrations[attr].cached:
                destructor(self, constructor_value, None)
            else:
                destructor(self, None)
        try:
            del self.__dict__[attr]
        except KeyError:
            # destructor might have deleted self.attr already
            pass

    def destroy(self, exception=None):
        """
        Cleans up this context and makes it unusable.

        After calling this function, this object will lose all its magic and
        behave like an empty class.

        The optional *exception*, that is the cause of this method call, will be
        passed to the destructors of every :term:`context member`.
        """
        if not self._active:
            return
        if exception:
            self.log.debug('Destroying, %s: %s',
                           type(exception).__name__, exception)
        else:
            self.log.debug('Destroying')
        tx = self.tx_manager.get()
        if exception or tx.isDoomed():
            tx.abort()
        else:
            tx.commit()
        self._active = False
        for attr in reversed(list(self._constructed_attrs.keys())):
            self.__delattr(attr, exception)
        for callback in self._conf._destroy_callbacks:
            callback(self, exception)
