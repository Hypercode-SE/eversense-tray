# Eversense Tray
Eversense tray is a python based tray app that runs on ubuntu to show the current glucose value from the Eversense CGM system.

To build the app you need the following system dependencies:
```bash
  sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-appindicator3-0.1 gir1.2-gdkpixbuf-2.0 python3-dbus
```

Then you need to create a python environment and install the dependencies:
```bash
  python3 -m venv .venv
  source .venv/bin/activate
  pip install poetry
  poetry install --with dev
```

Finally if you want to create an executable for running on startup:
```bash
  pyinstaller --onefile --noconfirm --clean --windowed main.py   --add-data "/usr/share/glib-2.0/schemas:usr/share/glib-2.0/schemas"   --add-data "/usr/share/icons:usr/share/icons"   --add-data "/usr/lib/x86_64-linux-gnu/gtk-3.0:usr/lib/x86_64-linux-gnu/gtk-3.0"
```

This should be run in the "/src" directory.

You will then get an executable that you can copy on your system to a system wide place (`/usr/local/bin` for example).

If you then copy the evensense-tray.desktop file into `~/.config/autostart/` it should start automatically when you login.
