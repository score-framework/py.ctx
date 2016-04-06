.. module:: score.ctx
.. role:: faint
.. role:: confkey

*********
score.ctx
*********

Every single interaction with an application is strongly tied to an
environment, where the interaction is taking place. There is probably an
authenticated user, a running database transaction, connections to remote
servers, etc.

This module provides a framework for defining the parameters of these
environments, allowing other modules to provide valuable information relevant
to the current interaction. It basically implements the `Context Object
Pattern`_.

A *context*, as defined by this module, can be regarded as a smaller sibling of
the HTTP session: It contains all required data to serve an HTTP request, for
example.

A context is not tied to interaction through HTTP, though. When a user opens a
shell to the application, the application should also create a new context,
where it could store the id of the authenticated user.

.. _Context Object Pattern: http://c2.com/cgi/wiki?ContextObject


.. _ctx_quickstart:

Quickstart
==========

Once the module is initialized, you can register :term:`context members
<context member>` by calling :meth:`score.ctx.ConfiguredCtxModule.register`:

>>> import random
>>> import score.ctx
>>> ctx_conf = score.ctx.init()
>>> ctx_conf.register('randnum', lambda: random.randint(0, 10))


These registered context members are available under the given name in every
:class:`Context`:

>>> ctx = ctx_conf.Context()
>>> ctx.randnum
4
>>> ctx.randnum
4
>>> ctx.randnum
4

As you can see, the value of the context member is cached by default. If you
want your value to be evaluated anew each time, you will have to disable
caching during registration:

>>> import random
>>> import score.ctx
>>> ctx_conf = score.ctx.init()
>>> ctx_conf.register('randnum', lambda: random.randint(0, 10), cached=False)
>>> ctx = ctx_conf.Context()
>>> ctx.randnum
2
>>> ctx.randnum
8


.. _ctx_configuration:

Configuration
=============

This module adheres to our :ref:`module initialization guiedlines
<module_initialization>`, but does not require any configuration: calling its
:func:`init` without arguments is sufficient:

>>> import score.ctx
>>> ctx_conf = score.ctx.init()


.. _ctx_details:

Details
=======


.. _ctx_transactions:

Transactions
------------

Every context object also provides an :interface:`ITransactionManager
<transaction.interfaces.ITransactionManager>`. This transaction manager will be
used to implement a :term: `context member` called `tx`, that contains a `zope
transaction`_. That transaction will be committed at the end of the
:class:`.Context` lifetime. This means that the application does not need to
operate on the global "current" transaction.

.. _zope transaction: http://zodb.readthedocs.org/en/latest/transactions.html


.. _ctx_member_destructor:

Member Destructors
------------------

It is possible to provide a member destructor for a member during registration:

.. code-block:: python

    def construct(ctx):
        if hasattr(ctx, 'session_id'):
            return load_session(ctx.session_id)
        return new_session()

    def destruct(ctx, session, exception):
        if exception:
            session.discard_changes()
        else:
            session.save()
            session.close()

    ctx_conf.register('session', construct, destruct)

As you can see, the destructor receives three arguments:

- The context object,
- the value returned by the constructor, and
- the exception, that terminated the context pre-maturely (or `None`, if the
  context terminated successfully).

The parameter list changes, though, if the context member is not cached: the
second parameter does not really exist in that case.

.. code-block:: python

    def construct(ctx):
        if not hasattr(ctx, '_num_calls'):
            ctx._num_calls = 0
        ctx._num_calls += 1

    def destruct(ctx, exception):
        count = ctx._num_calls if hasattr(ctx, '_num_calls') else 0
        logger.debug('Counter called %d times', count)

    ctx_conf.register('counter', construct, destruct, cached=False)


.. _ctx_api:

API
===

Configuration
-------------

.. autofunction:: score.ctx.init

.. autoclass:: score.ctx.ConfiguredCtxModule

    .. attribute:: Context

        A configured :class:`.Context` class, which can be instantiated directly:

        >>> ctx = ctx_conf.Context()

    .. automethod:: score.ctx.ConfiguredCtxModule.register

    .. automethod:: score.ctx.ConfiguredCtxModule.on_create

    .. automethod:: score.ctx.ConfiguredCtxModule.on_destroy

.. autoclass:: score.ctx.Context

    .. automethod:: score.ctx.Context.destroy
