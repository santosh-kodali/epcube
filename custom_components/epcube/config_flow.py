import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
import aiohttp
import logging
from .const import DOMAIN, DEFAULT_SCAN_INTERVAL, CONF_SCALE_POWER, CONF_ENABLE_TOTAL, CONF_ENABLE_ANNUAL, CONF_ENABLE_MONTHLY

_LOGGER = logging.getLogger(__name__)

class EpCubeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self._errors = {}

    async def async_step_user(self, user_input=None):
        self._errors = {}

        if user_input is not None:
            token = user_input["token"].strip()
            if not token.startswith("Bearer "):
                token = f"Bearer {token}"

            sn = await self._get_sn_from_token(token)

            if not sn:
                self._errors["base"] = "sn_not_found"
            else:
                for entry in self._async_current_entries():
                    if entry.data.get("sn") == sn:
                        return self.async_abort(reason="already_configured")

                await self.async_set_unique_id(sn)
                return self.async_create_entry(
                    title=f"EpCube {sn}",
                    data={
                        "token": token,
                        "sn": sn,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("token"): str,
            }),
            errors=self._errors,
        )

    async def _get_sn_from_token(self, token):
        url = "https://monitoring-us.epcube.com/api/user/user/base"
        headers = {
            "accept": "*/*",
            "accept-language": "it-IT",
            "accept-encoding": "gzip, deflate, br",
            "user-agent": "ReservoirMonitoring/2.1.0 (iPhone; iOS 18.3.2; Scale/3.00)",
            "authorization": token
        }
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        _LOGGER.debug("Risposta user/base: %s", data)
                        return data.get("data", {}).get("defDevSgSn")
                    else:
                        _LOGGER.error("Errore HTTP %s nella richiesta user/base", response.status)
            except Exception as e:
                _LOGGER.exception("Errore durante la richiesta user/base: %s", e)
            return None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return EpCubeOptionsFlow(config_entry)

class EpCubeOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            token = user_input.get("token", "").strip()
            if not token.startswith("Bearer "):
                token = f"Bearer {token}"
            return self.async_create_entry(title="", data={
                "token": token,
                "scan_interval": user_input.get("scan_interval", DEFAULT_SCAN_INTERVAL),
                CONF_SCALE_POWER: user_input.get(CONF_SCALE_POWER, False),
                CONF_ENABLE_TOTAL: user_input.get(CONF_ENABLE_TOTAL, False),
                CONF_ENABLE_ANNUAL: user_input.get(CONF_ENABLE_ANNUAL, False),
                CONF_ENABLE_MONTHLY: user_input.get(CONF_ENABLE_MONTHLY, False),
            })

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional("token", default=self._config_entry.data.get("token")): str,
                vol.Optional("scan_interval", default=self._config_entry.options.get("scan_interval", DEFAULT_SCAN_INTERVAL)): int,
                vol.Optional(CONF_ENABLE_TOTAL, default=self._config_entry.options.get(CONF_ENABLE_TOTAL, False)): bool,
                vol.Optional(CONF_ENABLE_ANNUAL, default=self._config_entry.options.get(CONF_ENABLE_ANNUAL, False)): bool,
                vol.Optional(CONF_ENABLE_MONTHLY, default=self._config_entry.options.get(CONF_ENABLE_MONTHLY, False)): bool,
            })
        )