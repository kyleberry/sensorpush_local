import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .const import (
    CONF_DAILY_AUDIT_HOUR,
    CONF_MAX_RETRIES,
    DEFAULT_DAILY_AUDIT_HOUR,
    DEFAULT_MAX_RETRIES,
    DOMAIN,
)


class SensorPushConfigFlow(
    config_entries.ConfigFlow, domain=DOMAIN
):  # pylint: disable=abstract-method
    """Handle a config flow for SensorPush Local."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(title="SensorPush Local", data={})

        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlowHandler()


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options for SensorPush Local."""

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_DAILY_AUDIT_HOUR,
                        default=options.get(
                            CONF_DAILY_AUDIT_HOUR, DEFAULT_DAILY_AUDIT_HOUR
                        ),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=0, max=23, step=1, mode=NumberSelectorMode.BOX
                        )
                    ),
                    vol.Optional(
                        CONF_MAX_RETRIES,
                        default=options.get(CONF_MAX_RETRIES, DEFAULT_MAX_RETRIES),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=0, max=5, step=1, mode=NumberSelectorMode.BOX
                        )
                    ),
                }
            ),
        )
