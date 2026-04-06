# Installation: Pi Zero 2W + Waveshare 2.13inch e-Paper HAT (G)

## 1. Flash the OS

Use **Raspberry Pi Imager** and choose:
- **OS:** Raspberry Pi OS Lite (64-bit) — no desktop, minimum overhead
- **Storage:** your microSD

In the imager's **Advanced options (⚙)** before writing:
- Set hostname (e.g. `btcticker`)
- Enable SSH
- Set WiFi SSID + password
- Set username/password (e.g. `pi`)
- Set locale/timezone

## 2. First Boot

SSH in after boot:
```bash
ssh pi@btcticker.local
```

Update the system:
```bash
sudo apt update && sudo apt full-upgrade -y
```

## 3. Enable SPI

```bash
sudo raspi-config nonint do_spi 0
sudo reboot
```

## 4. Efficiency Tweaks

After reboot, edit `/boot/firmware/config.txt`:
```bash
sudo nano /boot/firmware/config.txt
```
Add at the bottom:
```ini
gpu_mem=16
dtoverlay=disable-bt
```

Disable WiFi power management (prevents disconnects on always-on):
```bash
sudo nano /etc/rc.local
```
Add before `exit 0`:
```bash
iwconfig wlan0 power off
```

Disable unused services:
```bash
sudo systemctl disable bluetooth hciuart avahi-daemon triggerhappy
sudo reboot
```

## 5. Install System Dependencies

```bash
sudo apt install -y git python3-pip \
    python3-matplotlib python3-pil python3-rpi.gpio \
    python3-yaml libopenblas0
```

> Installing matplotlib/Pillow/RPi.GPIO via `apt` uses pre-compiled packages — much faster than `pip` on Pi Zero 2W.

## 6. Clone the Repo

```bash
cd ~
git clone https://github.com/YOUR_FORK_URL/btcticker.git
cd btcticker
```

## 7. Install Waveshare e-Paper Library

```bash
cd ~
git clone --depth=1 https://github.com/waveshare/e-Paper.git
cp -r e-Paper/RaspberryPi_JetsonNano/python/lib/waveshare_epd ~/btcticker/
rm -rf ~/e-Paper
```

Verify the driver file exists:
```bash
ls ~/btcticker/waveshare_epd/epd2in13g.py
```

## 8. Install Remaining Python Dependencies

```bash
cd ~/btcticker
python3 -m pip install --user -r requirements.txt
```

## 9. Configure

```bash
cp config_example.yaml config.yaml
nano config.yaml
```

Recommended settings for always-on use:
```yaml
display:
  orientation: 90     # landscape, buttons on left
  cycle: true
  cyclefiat: false
  inverted: false
ticker:
  currency: bitcoin
  fiatcurrency: usd
  sparklinedays: 1
  updatefrequency: 300  # 5 min minimum — respect CoinGecko rate limits
```

## 10. Test Run

```bash
cd ~/btcticker
python3 btcticker2in13g.py --log debug
```

First run fetches the coin logo and may take ~30s. Check for errors before proceeding.

## 11. Set Up as a Service (Always-On)

```bash
sudo nano /etc/systemd/system/btcticker.service
```

```ini
[Unit]
Description=Bitcoin Ticker ePaper Display
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/btcticker
ExecStart=/usr/bin/python3 /home/pi/btcticker/btcticker2in13g.py
Restart=always
RestartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable btcticker
sudo systemctl start btcticker
```

Check it's running:
```bash
sudo systemctl status btcticker
journalctl -u btcticker -f
```

After a reboot, the service starts automatically and the display updates within ~30s of getting a network connection.

## 12. Auto-Update on Git Push

The device polls GitHub every 5 minutes and restarts itself when new commits are detected.

**Allow the service user to restart btcticker without a password:**
```bash
echo 'pi ALL=(ALL) NOPASSWD: /bin/systemctl restart btcticker' \
  | sudo tee /etc/sudoers.d/btcticker-update
sudo chmod 440 /etc/sudoers.d/btcticker-update
```

**Make the update script executable:**
```bash
chmod +x ~/btcticker/autoupdate.sh
```

**Create a systemd timer:**
```bash
sudo tee /etc/systemd/system/btcticker-update.service > /dev/null <<'EOF'
[Unit]
Description=Check for btcticker updates on GitHub

[Service]
Type=oneshot
User=pi
ExecStart=/home/pi/btcticker/autoupdate.sh
StandardOutput=journal
StandardError=journal
EOF

sudo tee /etc/systemd/system/btcticker-update.timer > /dev/null <<'EOF'
[Unit]
Description=Run btcticker update check every 5 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
Unit=btcticker-update.service

[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now btcticker-update.timer
```

Verify it's active:
```bash
systemctl status btcticker-update.timer
journalctl -u btcticker-update.service -f
```

Now pushing to `main` on GitHub will be picked up within 5 minutes and the display will restart automatically.
