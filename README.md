# Balboa Spa Easyconf

A Balboa spa in Home Assistant on its BWA Wi-Fi module, locally, with what it
uses: power and energy for the whole spa and for each part, worked out from
which parts run at the moment, and learned from a meter if you have one.

Everything Home Assistant's own Balboa integration does is here too: the
thermostat (ready or rest, set temperature, low or high range), each pump at
its speeds, the blower, the lights, aux and mister outputs, the filter cycles'
times, the clock and the fault log. Names come in Swedish or English.

## What the spa uses

The spa's power is the sum over its parts at the level each is at:

| Part | Runs when | Typical power (230 V) |
|---|---|---|
| Heater | the spa reports *heating* (not *waiting for heat*) | 3000 W |
| Pump, two-speed | low / high | 400 W / 1500 W |
| Pump, one-speed | on | 1500 W |
| Blower | on | 700 W |
| Circulation pump | on | 100 W |
| Light | on | 10 W |
| Controller and Wi-Fi | always, while the spa answers | 10 W |

Set the real figures when adding the spa, or later under *Configure*: there is
a field per level of every part the spa reports. The figures in the table are
the defaults; on the BP2100G1 this was built for, the house's grid meter
showed the heater at 2.95 kW, pump 1 at 435 W on low and pump 2 at 2.0 kW.

From that come:

* **Power** (W), with the parts that draw something in its attributes, and a
  power sensor per part;
* **Energy** (kWh, total increasing) for the whole spa and per part, ready for
  the Energy dashboard as an individual device. Each power is held until the
  next change, so the sum is exact for the model; nothing is counted while the
  spa does not answer.

### Learning from a meter

Pick a power sensor whose reading includes the spa (the house's consumption,
one phase of it, or a metering plug) and the integration measures each part
itself. Every time a part switches on or off while the rest of the spa stays
as it is for 30 seconds before and after, it compares the meter's median
before and after. When a pump and the heater switch within a few seconds of
each other, the step is shared out once one of them is known. A step with the
wrong sign or out of range (something else in the house switched at the same
moment) is dropped.

Once a level has three measurements, the median of its last 25 replaces the
figure you set (turn that off with *Use learned powers*). Each learned value
is a diagnostic sensor with its measurements in the attributes; *Forget
learned powers* starts over. The meter should report at least every ten
seconds; one that only reports changes works too. It must count what the house
uses as positive watts (a grid meter that shows import as negative will not do).

## One connection at a time

The BWA module takes one TCP client. While Home Assistant's own Balboa
integration (or the Balboa app on the local network, or *Spa Client*) is
connected, this one cannot connect, and the set-up says so. Disable or remove
the other one for the same spa first.

## Install

Needs Home Assistant 2026.9 or later (tested on 2026.9.2 and 2026.11.3).

**HACS** → Custom repositories → `https://github.com/beolink/HA-Balboa-Spa-Easyconf`
as an Integration → download → restart Home Assistant.

**By hand**: copy `custom_components/balboa_easyconf/` into your
`config/custom_components/` and restart.

## Set up

*Settings → Devices & services → Add integration → Balboa Spa Easyconf.* The
form offers a spa found on the network (the module answers a UDP broadcast on
port 30303; DHCP discovery works too) or takes an address. The integration
then connects once to read the spa's model and parts, and asks what each part
draws.

## Notes

* pybalboa 1.1 reads the blower from the wrong bits of the status message, so
  a running one-speed blower shows as unknown in Home Assistant's own Balboa
  integration. This one reads the blower from the status byte itself (bits 2-3
  of byte 13).
* Pumps, blowers, lights, aux and misters are switched by presses, as on the
  panel: each press steps the part to its next speed, off after the last. The
  presses are counted from the level last asked for until the spa shows it, so
  "on" straight after "off" does what it says.
* Moving a filter cycle's start keeps its length; changing its end changes its
  length (15 minutes to 24 hours).
* *Off* on the thermostat is the spa's rest mode, as in Home Assistant's own
  integration: it then heats only during the filter cycles.
* With *Keep the spa's clock right* on, the spa's clock is set from Home
  Assistant once an hour when it is more than a minute off. The filter cycles
  run by that clock.

## Development

```bash
pip install "homeassistant==2026.11.3" "pybalboa>=1.1.3,<2" pytest pytest-asyncio
pytest
python scripts/smoke_real_ha.py   # a real Home Assistant against a stand-in BWA module
python scripts/build_strings.py   # after changing a text: writes strings.json and translations
```

`tests/fakespa.py` is the stand-in module: it speaks the BWA protocol on TCP,
takes one client at a time and plays the BP2100G1's configuration.
