from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import EntityCategory
from .const import DOMAIN

import logging
import aiohttp

_LOGGER = logging.getLogger(__name__)

MODE_MAP = {
    "1": "Autoconsumo",
    "3": "Backup",
#    "2": "Tempo di utilizzo"
}
REVERSE_MODE_MAP = {v: k for k, v in MODE_MAP.items()}


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([EpCubeModeSelect(coordinator, entry)], True)


class EpCubeModeSelect(CoordinatorEntity, SelectEntity):
    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.entry = entry
        self.entity_description = SelectEntityDescription(
            key="workstatus",
            name="EP CUBE Modalità",
            icon="mdi:transmission-tower",
            entity_category=EntityCategory.CONFIG
        )
        self._attr_unique_id = "epcube_mode_select"
        self._attr_options = list(MODE_MAP.values())
        self._attr_device_info = {
            "identifiers": {("epcube", "epcube_device")},
            "name": "EP CUBE",
            "manufacturer": "CanadianSolar",
        }

    @property
    def current_option(self):
        raw = str(self.coordinator.data["data"].get("workstatus"))
        return MODE_MAP.get(raw, "Sconosciuto")

    async def async_select_option(self, option: str):
        mode = REVERSE_MODE_MAP.get(option)
        if not mode:
            _LOGGER.warning("Modalità non valida selezionata: %s", option)
            return

        payload = {
            "devId": self.coordinator.data["data"].get("devid"),
            "workStatus": mode,
            "weatherWatch": "0",
            "onlySave": "0",
        }

        # Aggiungi il SOC corretto in base alla modalità
        if mode == "1":  # Autoconsumo
            payload["selfConsumptioinReserveSoc"] = str(self.coordinator.data["data"].get("selfconsumptioinreservesoc", 15))
        elif mode == "3":  # Backup
            payload["backupPowerReserveSoc"] = str(self.coordinator.data["data"].get("backuppowerreservesoc", 50))
        

        _LOGGER.debug("Invio payload switchMode (modalità): %s", payload)
        await self._post_switch_mode(payload)

    async def _post_switch_mode(self, payload):
        url = "https://monitoring-us.epcube.com/api/device/switchMode"
        headers = {
            "accept": "*/*",
            "content-type": "application/json",
            "authorization": self.entry.data.get("token"),
            "user-agent": "ReservoirMonitoring/2.1.0 (iPhone; iOS 18.3.2; Scale/3.00)",
            "accept-language": "it-IT",
            "accept-encoding": "gzip, deflate, br",
        }

        _LOGGER.debug("Invio payload switchMode (modalità): %s", payload)

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                text = await resp.text()
                if resp.status != 200:
                    _LOGGER.error("Errore nel cambio modalità EP Cube: %s", text)
                else:
                    _LOGGER.info("Modalità EP Cube aggiornata correttamente. Risposta: %s", text)
                    await self.coordinator.async_request_refresh()
    
