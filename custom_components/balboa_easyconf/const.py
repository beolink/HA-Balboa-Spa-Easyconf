"""Constants for Balboa Spa Easyconf."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "balboa_easyconf"
MANUFACTURER: Final = "Balboa Water Group"

#: The BWA Wi-Fi module's TCP port. It takes one client at a time.
DEFAULT_PORT: Final = 4257

#: entry.data: the parts the spa reported, {component id: [levels]}.
CONF_COMPONENTS: Final = "components"
CONF_MAC: Final = "mac"
CONF_MODEL: Final = "model"

#: entry.options: one watt figure per power key, as "power_<key>".
POWER_PREFIX: Final = "power_"
#: entry.options: a power sensor that measures the spa among other things.
CONF_REFERENCE: Final = "reference_sensor"
#: entry.options: use powers learned from the reference sensor.
CONF_USE_LEARNED: Final = "use_learned"
#: entry.options: keep the spa's clock on Home Assistant's time.
CONF_SYNC_TIME: Final = "sync_time"

STORE_VERSION: Final = 1
