# Copyright © 2015 STRG.AT GmbH, Vienna, Austria
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

"""
This package :ref:`integrates <framework_integration>` the module with
pyramid_.

.. _pyramid: http://docs.pylonsproject.org/projects/pyramid/en/latest/
"""
import functools
from pyramid.tweens import EXCVIEW
from types import MethodType


def init(confdict, configurator):
    """
    Apart from calling the :func:`base initializer <score.ctx.init>`, this
    function will also register a :term:`tween` creating a new :class:`.Context`
    for every request. The tween will also add a member `ctx` to all request
    objects. If you configured :mod:`score.db`, for example, you could query
    users like the following:

    >>> request.ctx.db.query(User).first()
    """
    configurator.add_tween('score.ctx.pyramid.tween_factory', under=EXCVIEW)
    import score.ctx
    ctx_conf = score.ctx.init(confdict)
    original_register = ctx_conf.register
    @functools.wraps(ctx_conf.register)
    def register(self, name, constructor, destructor=None, cached=True):
        if name != 'score':
            configurator.add_request_method(
                lambda request: getattr(request.ctx, name),
                name, property=cached)
        return original_register(name, constructor, destructor, cached)
    ctx_conf.register = MethodType(register, ctx_conf)
    return ctx_conf


def tween_factory(handler, registry):

    def tween(request):
        ctx = request.score.ctx.Context()
        ctx.request = request
        request.ctx = ctx
        try:
            response = handler(request)
            ctx.response = response
            ctx.destroy()
            return response
        except Exception as e:
            ctx.response = None
            ctx.destroy(e)
            raise

    return tween
