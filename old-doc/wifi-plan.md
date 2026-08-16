# Raspberry Pi field Wi-Fi plan

## Goal

The stage system should work without venue Ethernet and without relying on venue
Wi-Fi. Recording must work offline. Local phone control should work even when the
internet does not.

The Raspberry Pi should provide its own private Wi-Fi network for control:

```text
SSID: recs-control
Phone/tablet: joins recs-control
Control UI: http://192.168.4.1
```

This can avoid both a built-in touchscreen case and a separate USB Wi-Fi dongle
for the basic local-control setup.

## Baseline topology

Use the Pi's built-in Wi-Fi as an access point:

```text
Phone/tablet
  -> Pi Wi-Fi hotspot
  -> recs local web UI or SSH

Raspberry Pi
  -> records locally
  -> no internet required
```

This is the minimum reliable field setup. It supports:

- checking recorder status;
- running calibration;
- starting or stopping optional streamer controls;
- seeing disk/input/buffer warnings;
- SSH fallback from a phone terminal app.

## Mixer control topology

The Behringer X18's built-in Wi-Fi access point is known to be unreliable. Avoid
using it as the main control network.

Instead, connect the X18 Ethernet port to the Raspberry Pi Ethernet port and use
the Pi as the local network point:

```text
Phone/tablet
  -> Pi Wi-Fi hotspot
  -> X AIR app
  -> Pi routes or bridges to Ethernet
  -> X18 Ethernet port
```

This uses:

- Pi built-in Wi-Fi for phone/tablet control;
- Pi Ethernet for mixer control;
- no USB Wi-Fi dongle.

The X AIR app must be able to discover the mixer through this network, or the
operator must be able to enter the mixer's IP address manually.

## Optional internet

Internet access is not part of the reliable baseline.

For Twitch or other streaming, there are separate options:

1. Add a USB Wi-Fi dongle for venue Wi-Fi or phone hotspot internet.
2. Use phone USB tethering if it proves reliable.
3. Skip streaming when internet is unavailable.

Do not make recording or local control depend on internet availability.

## Implementation notes

The network setup belongs to the Pi OS and daemon install flow, not to the audio
recorder core.

The installer should configure:

1. A private access point on the Pi's built-in Wi-Fi.
2. A static Pi control address, for example `192.168.4.1`.
3. DHCP for phones/tablets joining the hotspot.
4. Routing or bridging between Wi-Fi and Ethernet so the phone can reach the X18.
5. A stable X18 address, either static or DHCP-reserved.

`recs` should assume this local network exists and expose control/status on it.
If the network service fails, local recording should continue.

## Risks and tests

The main risks are discovery and routing:

- The X AIR app may not auto-discover the mixer across the Pi's Wi-Fi/Ethernet
  boundary.
- Manual mixer IP entry may be required.
- Bridging can be fussier than routing on Wi-Fi access points.
- The Pi must not become a single point of failure for audio itself; if the Pi
  crashes, mixer audio should continue even though phone mixer control may be
  lost.

Test before relying on this live:

1. Configure Pi hotspot.
2. Connect phone to `recs-control`.
3. Connect Pi Ethernet to X18 Ethernet.
4. Verify `recs` local UI works from the phone.
5. Verify X AIR app can control the mixer.
6. Power-cycle the Pi and mixer and confirm the network recovers.

## Additional work beyond the prompt

None.
