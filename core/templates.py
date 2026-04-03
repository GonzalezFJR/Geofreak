"""Shared Jinja2 templates instance with i18n globals."""

import hashlib
import os
import time

from fastapi.templating import Jinja2Templates

from core.i18n import t, t_js, game_field

_templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")

# Cache-busting version: changes on every app restart (deploy)
_ASSET_VERSION = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]

templates = Jinja2Templates(directory=_templates_dir)
templates.env.globals["t"] = t
templates.env.globals["t_js"] = t_js
templates.env.globals["game_field"] = game_field
templates.env.globals["V"] = _ASSET_VERSION
