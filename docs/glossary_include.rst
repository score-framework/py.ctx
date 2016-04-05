.. _ctx_glossary:

.. glossary::

    context object
        An object that has the same lifetime as any interaction with the
        application. Have a look at the documentation of :mod:`score.ctx` for a
        more elaborate definition.

    context member
        A dynamically created member of a :class:`Context <score.ctx.Context>`
        class. Context members are registered by calling
        :meth:`score.ctx.ConfiguredCtxModule.register`. The :ref:`introduction
        to score.ctx <ctx_quickstart>` provides some examples.
