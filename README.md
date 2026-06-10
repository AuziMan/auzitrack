# AuziTrack — Phoenix Flight Tracker

Live ADS-B flight tracker running on a Raspberry Pi. Displays nearby aircraft with altitude, speed, heading, signal strength, and origin/destination lookup.

---

## Hardware

- Raspberry Pi
- RTL2838 USB dongle (RTL-SDR)
- Bingfu Dual Band 978/1090MHz magnetic antenna

---

## First-Time Setup (Pi)

```bash
cd ~/projects/flight-trackerv2
git clone git@github.com:YOUR_USERNAME/auzitrack.git
cd auzitrack
./setup.sh
```

`setup.sh` installs the Python venv, symlinks `index.html` into dump1090's web root, and registers the tracker as a systemd service that starts on boot.

---

## Starting the Tracker

**Step 1 — SSH into the Pi:**
```bash
ssh auziman@192.168.0.100
```

**Step 2 — Start dump1090:**
```bash
cd ~/projects/flight-tracker-antenna/dump1090
./dump1090 --net --write-json /home/auziman/projects/flight-tracker-antenna/dump1090/public_html --quiet --lat 33.4484 --lon -112.0740
```

Leave this terminal open. dump1090 writes live aircraft data every second.

**Step 3 — The tracker service starts automatically.** Verify it's running:
```bash
sudo systemctl status tracker
```

**Step 4 — Open in browser:**
```
http://192.168.0.100
```

---

## Stopping the Tracker

**Stop dump1090:** `Ctrl+C` in the terminal where it's running.

**Stop the tracker service:**
```bash
sudo systemctl stop tracker
```

---

## Updating After a Code Change

```bash
# On your Mac
git push

# On the Pi
git pull && sudo systemctl restart tracker
```

---

## Troubleshooting

**Page shows stale data / not updating**
- Check dump1090 is running — it must be started manually each session
- Verify `aircraft.json` is being written:
  ```bash
  watch -n1 'stat /home/auziman/projects/flight-tracker-antenna/dump1090/public_html/aircraft.json'
  ```
  The `Modify` time should tick every second.

**Tracker service not running**
```bash
sudo systemctl restart tracker
sudo journalctl -u tracker -n 30
```

**Can't SSH from Mac**
```bash
sudo route delete -net 192.168.0.0/24
```

**lighttpd not serving the page**
```bash
sudo systemctl restart lighttpd
```

---

## Service Reference

| What | Command |
|------|---------|
| Tracker status | `sudo systemctl status tracker` |
| Restart tracker | `sudo systemctl restart tracker` |
| Tracker logs | `sudo journalctl -u tracker -f` |
| lighttpd status | `sudo systemctl status lighttpd` |
| Restart lighttpd | `sudo systemctl restart lighttpd` |
