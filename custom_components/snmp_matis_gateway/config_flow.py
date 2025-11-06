from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from .const import DOMAIN, CONF_READ_COMMUNITY, CONF_WRITE_COMMUNITY

class SnmpMatisConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            # very light validation
            host = user_input.get(CONF_HOST)
            if not host:
                errors["base"] = "host_missing"
            if not errors:
                return self.async_create_entry(title=host, data=user_input)

        schema = vol.Schema({
            vol.Required(CONF_HOST): str,
            vol.Optional(CONF_READ_COMMUNITY, default="public"): str,
            vol.Optional(CONF_WRITE_COMMUNITY, default="private"): str,
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)