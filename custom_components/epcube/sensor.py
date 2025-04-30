from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed, CoordinatorEntity
from homeassistant.const import UnitOfEnergy, UnitOfPower, PERCENTAGE
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass, SensorEntityDescription, SensorEntity
from homeassistant.helpers.entity import EntityCategory
from homeassistant.util import dt as dt_util
from homeassistant.helpers.entity_registry import async_get, RegistryEntryDisabler


from .const import DOMAIN, DEFAULT_SCAN_INTERVAL, CONF_ENABLE_TOTAL, CONF_ENABLE_ANNUAL, CONF_ENABLE_MONTHLY
import aiohttp
import async_timeout
from datetime import timedelta, datetime

import logging
_LOGGER = logging.getLogger(__name__)

def generate_sensors(data, enable_total=False, enable_annual=False, enable_monthly=False):
    """Genera i sensori per i dati ricevuti."""
    sensors = []

    suffix_map = {
        "_total": "Totale",
        "_annual": "Annuale",
        "_monthly": "Mensile"
    }

    disabled_by_variant = {
        "batterysoc": ["annual", "monthly", "total"],
        "solarflow": ["annual", "monthly", "total"],
        "solarpower": ["annual", "monthly", "total"],
        "backuppower": ["annual", "monthly", "total"],
        "backupflowpower": ["annual", "monthly", "total"],
        "gridhalfpower": ["annual", "monthly", "total"],
        "gridtotalpower": ["annual", "monthly", "total"],
        "gridpower": ["annual", "monthly", "total"],
        "solardcelectricity": ["annual", "monthly", "total"],
        "solaracelectricity": ["annual", "monthly", "total"],
    }
    diagnostic_sensors = [
        "status", "systemstatus", "workstatus", "isalert", "isfault",
        "backuploadsmode", "backuptype", "deftimezone", "devid",
        "faultwarningtype", "fromtimezone", "fromtype", "generatorlight",
        "gridlight", "isnewdevice", "off_on_grid_hint", "payloadversion",
        "ressnumber", "version", "evlight", "defcreatetime", "fromcreatetime",
        "gridpowerfailurenum", "activationdata", "warrantydata", "modeltype",
        "allowchargingxiagrid", "daylightsavingtime", "offgridpowersupplytime",
        "onlysave", "selfhelprate",
        #Sensori di 'tempo di utilizzo'
        "activeweek", "activeweeknonworkday", "activeweeknonworkday",
        "daylightactiveWeek", "dayLightActiveweeknonWorkday", "daytype",
        "isDayLightSaving", "weatherWatch",
    ]

    disabled_by_default = [
        "defcreatetime", "fromcreatetime",
        "allowchargingxiagrid", "daylightsavingtime", "offgridpowersupplytime",
        "onlysave",
        #disabilito i sensori 'tempo di utilizzo'
        "activeweek", "activeweeknonworkday", "activeWeekNonWorkDay",
        "daylightactiveweek", "dayLightActiveWeekNonWorkDay", "dayType",
        "isDayLightSaving", "weatherWatch",
    ]

    diagnostic_sensors = [s.lower() for s in diagnostic_sensors]
    disabled_by_default = [s.lower() for s in disabled_by_default]

    disabled_by_variant = {
        k.lower(): [v.lower() for v in vals]
        for k, vals in disabled_by_variant.items()
    }

    for key, value in data.items():
        key_lower = key.lower()
        entity_category = None

        suffix_label = ""
        base_key = key_lower
        for suffix, label in suffix_map.items():
            if key_lower.endswith(suffix):
                base_key = key_lower.removesuffix(suffix)
                suffix_label = suffix[1:]
                break

        if suffix_label in disabled_by_variant.get(base_key, []):
            continue

        if base_key in diagnostic_sensors:
            entity_category = EntityCategory.DIAGNOSTIC

        #ectricity = kWh
        #power = kW (none)
        #power (i numeri arrivano in watt) = W
        
        if "electricity" in base_key or "flow" in base_key:  # kWh
            #_LOGGER.debug("Energy kWh: %s", base_key)
            device_class = SensorDeviceClass.ENERGY
            unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
            state_class = SensorStateClass.TOTAL_INCREASING
        elif "power" in base_key:  # W
            #_LOGGER.debug("Power W: %s", base_key)
            device_class = SensorDeviceClass.POWER
            unit_of_measurement = UnitOfPower.WATT #KILO_WATT
            state_class = SensorStateClass.MEASUREMENT

        elif "soc" in base_key:
            #device_class = SensorDeviceClass.BATTERY #Causa problema con la batteria epcbube
            unit_of_measurement = PERCENTAGE
            state_class = SensorStateClass.MEASUREMENT

            if base_key == "batterysoc":
                device_class = SensorDeviceClass.BATTERY
                entity_category = None
            else:
                entity_category = EntityCategory.DIAGNOSTIC

        else:
            device_class = None
            unit_of_measurement = None
            state_class = None

        if base_key == "batterysoc":
            entity_registry_enabled_default = True

        elif key_lower.endswith("_annual"):
            entity_registry_enabled_default = enable_annual
        elif key_lower.endswith("_monthly"):
            entity_registry_enabled_default = enable_monthly
        elif key_lower.endswith("_total"):
            entity_registry_enabled_default = enable_total

        elif value is None:
            entity_registry_enabled_default = False
        elif base_key in disabled_by_default:
            entity_registry_enabled_default = False
        else:
            entity_registry_enabled_default = True

        translation_key = f"{base_key}_{suffix_label}" if suffix_label else base_key
        sensor = SensorEntityDescription(
            key=key,
            translation_key=translation_key,
            native_unit_of_measurement=unit_of_measurement,
            device_class=device_class,
            entity_category=entity_category,
            state_class=state_class,
            entity_registry_enabled_default=entity_registry_enabled_default
        )

        sensors.append(sensor)

    return sensors

async def fetch_device_info(session, token, dev_id):
    url = f"https://monitoring-eu.epcube.com/api/device/userDeviceInfo?devId={dev_id}"
    headers = {
        "accept": "*/*",
        "accept-language": "it-IT",
        "accept-encoding": "gzip, deflate, br",
        "user-agent": "ReservoirMonitoring/2.1.0 (iPhone; iOS 18.3.2; Scale/3.00)",
        "authorization": f"Bearer {token}"
    }

    async with session.get(url, headers=headers) as resp:
        json_data = await resp.json()
        raw_data = json_data.get("data", {})
        normalized = {k.lower(): v for k, v in raw_data.items()}
        return normalized

async def fetch_epcube_stats(session, token, dev_id, date_str, scope_type):
    url = f"https://monitoring-eu.epcube.com/api/device/queryDataElectricityV2?devId={dev_id}&queryDateStr={date_str}&scopeType={scope_type}"
    headers = {
        "accept": "*/*",
        "accept-language": "it-IT",
        "accept-encoding": "gzip, deflate, br",
        "user-agent": "ReservoirMonitoring/2.1.0 (iPhone; iOS 18.3.2; Scale/3.00)",
        "authorization": f"Bearer {token}"
    }

    async with session.get(url, headers=headers) as resp:
        json_data = await resp.json()
        #_LOGGER.debug("Risposta JSON (%s - %s): %s", scope_type, date_str, json_data)
        raw_data = json_data.get("data", {})
        normalized = {k.lower(): v for k, v in raw_data.items()}
        #_LOGGER.debug("Nomalized: %s" %normalized)
        return normalized

async def async_update_data_with_stats(session, url, headers, dev_id_sn, token):
    try:
        with async_timeout.timeout(15):
            async with session.get(url, headers=headers) as resp:
                if resp.content_type != "application/json":
                    raise UpdateFailed(f"Tipo MIME non gestito: {resp.content_type}")

                live_data = await resp.json()
                full_data_raw = live_data.get("data", {})
                #_LOGGER.debug("Full Data: %s", %full_data_raw)
                full_data = {k.lower(): v for k, v in full_data_raw.items()}
                real_dev_id = full_data.get("devid")

                now = datetime.now()
                year_str = str(now.year)
                month_str = now.strftime("%Y-%m")
                today_str = now.strftime("%Y-%m-%d")
                
                # Statistiche: live (scopeType=1), totale (scopeType=0), annuale (3), mensile (2)
                live_data = await fetch_epcube_stats(session, token, real_dev_id, today_str, 1)
                total_data = await fetch_epcube_stats(session, token, real_dev_id, year_str, 0)
                annual_data = await fetch_epcube_stats(session, token, real_dev_id, year_str, 3)
                monthly_data = await fetch_epcube_stats(session, token, real_dev_id, month_str, 2)
                
                device_info = await fetch_device_info(session, token, real_dev_id)
                
                switch_url = f"https://monitoring-eu.epcube.com/api/device/getSwitchMode?devId={real_dev_id}"
                async with session.get(switch_url, headers=headers) as switch_resp:
                    switch_json = await switch_resp.json()
                    #_LOGGER.debug("Risposta getSwitchMode: %s", switch_json)
                    switch_data = switch_json.get("data", {})
                    for k, v in switch_data.items():
                        full_data[k.lower()] = v  # Normalizza in lowercase
                
                for k in ["activationdata", "warrantydata", "modeltype", "batterycapacity"]:
                    full_data[k] = device_info.get(k)
                 
                INCLUDED_LIVE_KEYS = {
                    "gridelectricity", "gridelectricityfrom", "gridelectricityto",
                    "solarelectricity", "backupelectricity", "selfhelprate", "treenum", "coal",
                }

                for k, v in live_data.items():
                    key_lower = k.lower()
                    if key_lower in INCLUDED_LIVE_KEYS:
                        full_data[key_lower] = v
                
                for k, v in total_data.items():
                    full_data[f"{k}_total"] = v
                for k, v in annual_data.items():
                    full_data[f"{k}_annual"] = v
                for k, v in monthly_data.items():
                    full_data[f"{k}_monthly"] = v

                #_LOGGER.debug("Dati finali unificati (live + total + annual + monthly): %s", full_data)
                return {"data": full_data}

    except Exception as err:
        #_LOGGER.error("Errore nell'aggiornamento dei dati: %s", err)
        raise UpdateFailed(f"Errore nell'aggiornamento dei dati: {err}")

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    options = entry.options
    enable_total = options.get(CONF_ENABLE_TOTAL, False)
    enable_annual = options.get(CONF_ENABLE_ANNUAL, False)
    enable_monthly = options.get(CONF_ENABLE_MONTHLY, False)

    if not coordinator.data or "data" not in coordinator.data:
        #_LOGGER.warning("Nessun dato disponibile dal coordinator, sensori non creati.")
        return

    filtered_data = coordinator.data["data"]
    
    sensors = generate_sensors(
        filtered_data,
        enable_total=enable_total,
        enable_annual=enable_annual,
        enable_monthly=enable_monthly
    )

    entities = []

    for sensor in sensors:
        entity = EpCubeSensor(coordinator, sensor)

        entities.append(entity)

    entities.append(EpCubeLastUpdateSensor(coordinator))

    async_add_entities(entities, True)

    entity_registry = async_get(hass)

    for entity in entities:
        if entity.entity_id is not None:
            if "_annual" in entity.entity_id:
                if enable_annual:
                    entity_registry.async_update_entity(entity.entity_id, disabled_by=None)
                else:
                    entity_registry.async_update_entity(entity.entity_id, disabled_by=RegistryEntryDisabler.DEVICE)
            elif "_monthly" in entity.entity_id:
                if enable_monthly:
                    entity_registry.async_update_entity(entity.entity_id, disabled_by=None)
                else:
                    entity_registry.async_update_entity(entity.entity_id, disabled_by=RegistryEntryDisabler.DEVICE)
            elif "_total" in entity.entity_id:
                if enable_total:
                    entity_registry.async_update_entity(entity.entity_id, disabled_by=None)
                else:
                    entity_registry.async_update_entity(entity.entity_id, disabled_by=RegistryEntryDisabler.DEVICE)
            
    return True

class EpCubeSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, description):
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.entity_description = description
        self._attr_unique_id = f"epcube_{description.key}"
        self._attr_has_entity_name = True
        #self._attr_name = f"EP CUBE {description.name}"
        self._attr_unit_of_measurement = description.native_unit_of_measurement
        self._attr_device_class = description.device_class
        self._attr_state_class = description.state_class
        self._attr_entity_category = description.entity_category
        self._attr_entity_id = f"sensor.epcubes_{description.key}"
        self._attr_device_info = {
            "identifiers": {("epcube", "epcube_device")},
            "name": "EP CUBE",
            "manufacturer": "CanadianSolar",
            "model": "EP CUBE",
            "entry_type": "service",
            "configuration_url": "https://monitoring-eu.epcube.com/"
        }


    @property
    def native_value(self):
        value = self.coordinator.data["data"].get(self.entity_description.key)

        if value is not None:
            if self.entity_description.device_class == SensorDeviceClass.POWER:
                try:
                    return round(float(value) * 10, 1)
                except (ValueError, TypeError):
                    return None
        return value
    
    

class EpCubeLastUpdateSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "EP CUBE Ultimo Aggiornamento"
        self._attr_unique_id = "epcube_last_update"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        return dt_util.utcnow()
