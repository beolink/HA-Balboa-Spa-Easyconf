# Changelog

## [0.1.0] - 2026-11-26

The first release: a Balboa spa on its BWA Wi-Fi module, locally, with what it
uses.

- **Everything Home Assistant's own Balboa integration does.** The thermostat
  (ready or rest, set temperature, low or high range), each pump at its
  speeds, the blower, the lights, aux and mister outputs, heat mode and
  temperature range, the filter cycles' start and end, the spa's clock and the
  last fault. Names in Swedish or English.
- **Power and energy for the whole spa and for each part.** The spa's power is
  the sum over its parts at the level each is at, with a figure per level set
  when adding the spa or under *Configure*. Each power is held until the next
  change and integrated to kWh, ready for the Energy dashboard; nothing is
  counted while the spa does not answer.
- **Powers learned from a meter.** Pick a power sensor that includes the spa,
  and every switch of a part with the rest of the spa quiet for 30 seconds
  around it is measured from the meter's median before and after. From three
  measurements, the median of the last 25 replaces the set figure.
- **A running blower shows as running.** pybalboa 1.1 reads the blower from
  the wrong bits of the status message; this reads bits 2-3 of byte 13.
- **On after off does what it says.** Presses are counted from the level last
  asked for until the spa shows it, not from the last status.
- **A filter cycle keeps its length when its start moves.** Changing its end
  changes its length (15 minutes to 24 hours).
- The spa's clock is set from Home Assistant once an hour when it is more
  than a minute off (can be turned off).
