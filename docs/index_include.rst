.. module:: score.ctx
.. role:: confkey
.. role:: confdefault

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
>>> fruits = [
...     'loganberries',
...     'passion fruit',
...     'orange',
...     'apple',
...     'grapefruit',
...     'pomegranate',
...     'greengage',
...     'grapes',
...     'lemon',
...     'plum',
...     'mango',
...     'cherry',
...     'banana']
>>> ctx_conf.register('fruit', lambda ctx: random.choice(fruits))
>>> ctx_conf._finalize()


These registered context members are available under the given name in every
:class:`Context`:

>>> ctx = ctx_conf.Context()
>>> ctx.fruit
'banana'
>>> ctx.fruit
'banana'
>>> ctx.fruit
'banana'

As you can see, the value of the context member is cached. If you want your
value to be dynamic, you can register a function instead:

>>> def random_fruit():
...     return random.coice(fruits)
... 
>>> ctx_conf.register('dynamic_fruit', lambda ctx: random_fruit)
>>> ctx_conf._finalize()
>>> ctx = ctx_conf.Context()
>>> ctx.dynamic_fruit()
'pomegranate'
>>> ctx.dynamic_fruit()
'apple'


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

.. _ctx_api:

API
===

Configuration
-------------

.. autofunction:: init

.. autoclass:: ConfiguredCtxModule

    .. attribute:: Context

        A configured :class:`.Context` class, which can be instantiated directly:

        >>> ctx = ctx_conf.Context()

        Note that this member is available only after the module was finalized.

    .. automethod:: register

    .. automethod:: on_create

    .. automethod:: on_destroy

.. autoclass:: Context

    .. automethod:: destroy
