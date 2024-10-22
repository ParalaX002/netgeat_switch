from __future__ import annotations
import logging
from datetime import timedelta

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from homeassistant.core import callback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


# def setup_platform(
#     hass: HomeAssistant,
#     config: ConfigType,
#     add_entities: AddEntitiesCallback,
#     discovery_info: DiscoveryInfoType | None = None,
# ) -> None:
#     """Setup the plateform with the entries"""
#     entities = []
#     for i in range(0, 16):
#         entities.append(NetgearPortEntity(hass, hass.data[DOMAIN], i))

#     add_entities(entities)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """
    Setup the entry"""
    entities = []
    switch = hass.data[DOMAIN]

    coordinator = NetGearPortCoordinator(hass, switch)

    for i in range(0, 16):
        entities.append(NetgearPortEntity(coordinator, i))

    await coordinator.async_config_entry_first_refresh()
    async_add_entities(entities)


class NetGearPortCoordinator(DataUpdateCoordinator):
    """Coordinator for the netgear API"""

    def __init__(self, hass, my_api):
        """Initialize my coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            # Name of the data. For logging purposes.
            name="NetgearSwitch",
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=timedelta(seconds=10),
        )
        self.m_api = my_api
        self.hass = hass

    async def _async_update_data(self):
        """Fetch data from API endpoint.

        This is the place to pre-process the data to lookup tables
        so entities can quickly look up their data.
        """
        await self.hass.async_add_executor_job(self.m_api.ask_port_info)


class NetgearPortEntity(CoordinatorEntity, SensorEntity):
    """Sensor information for a netgear switch"""

    _attr_name = "Port Power"
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, port):
        """Pass coordinator to CoordinatorEntity."""
        super().__init__(coordinator, context=port)
        self.idx = port

        self.m_port = port
        self.m_api = coordinator.m_api
        self.m_port_status = []

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID"""
        name = self.m_api.get_switch_name()
        if not name:
            return None
        return f"{name}_port{self.m_port + 1}_power"

    @property
    def name(self) -> str | None:
        """Return the name of the sensor"""
        return f"Port {self.m_port + 1} power"

    @property
    def native_value(self) -> float | None:
        """Return the value of the sensor"""
        print("Asking native value on port " + str(self.m_port))
        if self.m_port < len(self.m_port_status):
            if float(self.m_port_status[self.m_port]["Power"]) < 30:
                return float(self.m_port_status[self.m_port]["Power"])
            # Power can't be higher than 30W: there is an issue with the value
            else: return 0
        return 0

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of the sensor"""
        return UnitOfPower.WATT

    @callback
    def _handle_coordinator_update(self) -> None:
        """Retrieve latest state."""
        self.m_port_status = self.m_api.get_port_status()

    @property
    def should_poll(self) -> bool:
        return True
