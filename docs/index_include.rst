.. module:: score.ctx
.. role:: faint
.. role:: confkey

*********
score.ctx
*********

Introduction
============

Every single interaction with an application is strongly tied to an
environment, where the interaction is taking place. There is probably an
authenticated user, a running database transaction, connections to remote
servers, etc.

This module provides a framework for defining the parameters of these
environments, allowing other modules to provide valuable information relevant
to the current interaction.

A :term:`context`, as defined by this module, can be regarded as a smaller
sibling of the HTTP session: It contains all required data to serve an HTTP
request, for example.

A context is not tied to interaction through HTTP, though. When a user opens a
shell to the application, for example, the application should create a new
context, where it could store the id of the authenticated user.


Zope Transaction
================

A configured instance of this module also provides an
:interface:`ITransactionManager <transaction.interfaces.ITransactionManager>`.
This transaction manager will be used to implement a :term: `context member`
called `tx`, that contains a `zope transactions`_, that will be committed at
the end of the :class:`.Context`'s lifetime. This means that the application
does not need to operate on globals—like a the global "current" transaction—any
more.

.. _zope transactions: http://zodb.readthedocs.org/en/latest/transactions.html


Configuration
=============

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
