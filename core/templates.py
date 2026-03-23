"""Shared Jinja2 templates instance with i18n globals."""

import os

from fastapi.templating import Jinja2Templates

from core.i18n import t, t_js, game_field

_templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")

templates = Jinja2Templates(directory=_templates_dir)
templates.env.globals["t"] = t
templates.env.globals["t_js"] = t_js
templates.env.globals["game_field"] = game_field
