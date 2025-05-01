from homeassistant.components.number import NumberEntity, NumberEntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.const import EntityCategory
from .const import DOMAIN

import aiohttp
import logging

_LOGGER = logging.getLogger(__name__)

SOC_KEYS = {
    "selfconsumptioinreservesoc": "selfConsumptioinReserveSoc",
    "backuppowerreservesoc": "backupPowerReserveSoc",
}

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([
        EpCubeDynamicSocNumber(coordinator, entry),
        EpCubeStaticSocNumber(coordinator, entry, "selfconsumptioinreservesoc", "SOC Autoconsumo", 0, 100),
        EpCubeStaticSocNumber(coordinator, entry, "backuppowerreservesoc", "SOC Backup", 50, 100),
    ], True)


class EpCubeDynamicSocNumber(CoordinatorEntity, NumberEntity):
    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self.entry = entry
        self.coordinator = coordinator
        self.entity_description = NumberEntityDescription(
            key="epcube_dynamic_soc",
            name="EPCUBE SOC Dinamico",
            icon="mdi:battery-charging",
            entity_category=EntityCategory.CONFIG,
        )
        self._attr_unique_id = "epcube_soc_dynamic"
        self._attr_step = 1
        self._attr_native_unit_of_measurement = "%"
        self._attr_device_info = {
            "identifiers": {("epcube", "epcube_device")},
            "name": "EPCUBE",
            "manufacturer": "CanadianSolar",
            "model": "EPCUBE",
            "entry_type": "service",
            "configuration_url": "https://monitoring-eu.epcube.com/"
        }

        if coordinator.data and coordinator.data.get("data"):
            mode = str(coordinator.data["data"].get("workstatus", ""))
        else:
            mode = ""

        if mode == "1":
            self._attr_min_value = 0
        else:
            self._attr_min_value = 50
        self._attr_max_value = 100

    @property
    def _mode(self):
        return str(self.coordinator.data.get("data", {}).get("workstatus", ""))

    @property
    def _soc_key(self):
        return {
            "1": "selfConsumptioinReserveSoc",
            "3": "backupPowerReserveSoc"
        }.get(self._mode)

    @property
    def native_value(self):
        value = self.coordinator.data.get("data", {}).get(self._soc_key.lower())
        _LOGGER.debug("SOC attuale (%s): %s", self._soc_key.lower(), value)
        return int(value) if value is not None else None
    
    
    

    async def async_set_native_value(self, value: float):
        dev_id = self.coordinator.data.get("data", {}).get("devid")
        work_status = self._mode

        key_original = self._soc_key
        payload = {
            "devId": dev_id,
            "workStatus": str(work_status),
            "weatherWatch": "0",
            "onlySave": "0",
            key_original: str(int(value)),
        }

        _LOGGER.debug("Invio payload switchMode (SOC dinamico): %s", payload)
        await self._post_switch_mode(payload)

    async def _post_switch_mode(self, payload):
        url = "https://monitoring-eu.epcube.com/api/device/switchMode"
        headers = {
            "Content-Type": "application/json",
            "Authorization": self.entry.data.get("token"),
            "User-Agent": "ReservoirMonitoring/2.1.0 (iPhone; iOS 18.3.2; Scale/3.00)",
            "Accept": "*/*",
            "Accept-Language": "it-IT",
            "Accept-Encoding": "gzip, deflate, br"
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                text = await resp.text()
                if resp.status != 200:
                    _LOGGER.error("Errore nell'invio SoC EP Cube dinamico: %s", text)
                else:
                    _LOGGER.info("SOC dinamico aggiornato correttamente. Risposta: %s", text)
                    await self.coordinator.async_request_refresh()


class EpCubeStaticSocNumber(CoordinatorEntity, NumberEntity):
    def __init__(self, coordinator, entry, key, name, min_val, max_val):
        super().__init__(coordinator)
        self.entry = entry
        self.coordinator = coordinator
        self.original_key = SOC_KEYS.get(key.lower(), key)
        self.entity_description = NumberEntityDescription(
            key=self.original_key,
            name=f"EPCUBE {name}",
            icon="mdi:battery-charging",
            entity_category=EntityCategory.CONFIG,
        )
        self._attr_unique_id = f"epcube_soc_{self.original_key}"
        self._attr_min_value = min_val
        self._attr_max_value = max_val
        self._attr_step = 1
        self._attr_native_unit_of_measurement = "%"
        self._attr_mode = "slider"
        self._attr_device_info = {
            "identifiers": {("epcube", "epcube_device")},
            "name": "EPCUBE",
            "manufacturer": "CanadianSolar",
            "model": "EPCUBE",
            "entry_type": "service",
            "configuration_url": "https://monitoring-eu.epcube.com/"
        }

    @property
    def native_value(self):
        value = self.coordinator.data.get("data", {}).get(self.original_key.lower())
        _LOGGER.debug("SOC statico attuale (%s): %s", self.original_key.lower(), value)
        return int(value) if value is not None else None
    

    async def async_set_native_value(self, value: float):
        dev_id = self.coordinator.data.get("data", {}).get("devid")
        work_status = self.coordinator.data.get("data", {}).get("workstatus")
        

        payload = {
            "devId": dev_id,
            "workStatus": str(work_status),
            "weatherWatch": "0",
            "onlySave": "0",
            self.original_key: str(int(value)),
        }

        _LOGGER.debug("Invio payload switchMode (SOC statico): %s", payload)
        await self._post_switch_mode(payload)

    async def _post_switch_mode(self, payload):
        url = "https://monitoring-eu.epcube.com/api/device/switchMode"
        headers = {
            "Content-Type": "application/json",
            "Authorization": self.entry.data.get("token"),
            "User-Agent": "ReservoirMonitoring/2.1.0 (iPhone; iOS 18.3.2; Scale/3.00)",
            "Accept": "*/*",
            "Accept-Language": "it-IT",
            "Accept-Encoding": "gzip, deflate, br"
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                text = await resp.text()
                if resp.status != 200:
                    _LOGGER.error("Errore nell'invio SoC EP Cube statico: %s", text)
                else:
                    _LOGGER.info("SOC statico aggiornato correttamente. Risposta: %s", text)
                    await self.coordinator.async_request_refresh()
