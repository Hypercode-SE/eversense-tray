import configparser
import datetime
import math
import random
import sys
import threading
import time
from pathlib import Path

from PIL import Image, ImageDraw

from eversense_client import EversenseClient
from glucose_db import GlucoseDB
import notify2
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import gi  # type: ignore

import pandas as pd

from login_dialog import LoginDialog

gi.require_version('Gtk', '3.0')
gi.require_version('AppIndicator3', '0.1')
from gi.repository import Gtk, GLib, AppIndicator3, GdkPixbuf  # type: ignore


class GlucoseApp:
    CONFIG_DIR = Path.home() / ".config" / "eversense-tray"
    CONFIG_FILE = CONFIG_DIR / "config.ini"
    DB_FILE = CONFIG_DIR / "glucose.db"

    LOW_THRESHOLD = 4.0
    HIGH_THRESHOLD = 15.0
    NORMAL_THRESHOLD_MIN = 5.0
    NORMAL_THRESHOLD_MAX = 10.0
    FETCH_INTERVAL_SEC = 5 * 60

    def __init__(self):
        self.config = configparser.ConfigParser()
        self.load_or_create_config()
        self.client = EversenseClient(self.config["auth"]["username"], self.config["auth"]["password"])
        self.db = GlucoseDB(self.DB_FILE)
        self.user_id = None
        self.low_alerted = False
        self.high_alerted = False
        self.current_glucose = None
        self.trend_arrow = "→"
        self.indicator = None
        self.popup_window = None
        self.fetch_thread = None

    def load_or_create_config(self):
        if not self.CONFIG_DIR.exists():
            self.CONFIG_DIR.mkdir(parents=True)
        if self.CONFIG_FILE.exists():
            self.config.read(self.CONFIG_FILE)
        else:
            dialog = LoginDialog()
            username = None
            password = None

            response = dialog.run()
            if response == Gtk.ResponseType.OK:
                username, password = dialog.get_credentials()

            elif response == Gtk.ResponseType.CANCEL:
                print("[Config] Login cancelled, exiting")
                sys.exit(0)

            dialog.destroy()

            self.config["auth"] = {}
            self.config["auth"]["username"] = username
            self.config["auth"]["password"] = password
            self.save_config()

    def save_config(self):
        with self.CONFIG_FILE.open("w") as f:
            self.config.write(f)

        print(f"[Config] Saved credentials to {self.CONFIG_FILE}")

    def setup_tray(self):
        self.indicator = AppIndicator3.Indicator.new(
            "eversense-glucose-tray",
            "dialog-information",
            AppIndicator3.IndicatorCategory.APPLICATION_STATUS)
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        self.indicator.set_menu(self.build_menu())

        self.update_tray_icon("blue")

    def build_menu(self):
        menu = Gtk.Menu()

        show_graph_item = Gtk.MenuItem(label="Show 24h Graph")
        show_graph_item.connect("activate", self.on_show_graph)
        menu.append(show_graph_item)

        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", self.on_quit)
        menu.append(quit_item)

        menu.show_all()
        return menu

    def generate_dot_icon(self, color, diameter=32):
        """Generate a circular dot icon and save it in the icons directory."""
        # Create a blank transparent image
        image = Image.new("RGBA", (diameter, diameter), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        # Calculate the center and radius
        center = diameter // 2
        radius = diameter // 2

        # Draw the circle
        draw.ellipse(
            (center - radius, center - radius, center + radius, center + radius),
            fill=color,
            outline=color,
        )

        # Save the image to the icons directory
        icons_dir = self.CONFIG_DIR / "icons"
        icons_dir.mkdir(exist_ok=True)  # Ensure the directory exists
        icon_path = icons_dir / f"{color}-dot.png"
        image.save(icon_path)
        return str(icon_path)

    def on_show_graph(self, _):
        if self.popup_window and self.popup_window.get_visible():
            self.popup_window.close()

        self.popup_window = self.create_graph_window()
        self.popup_window.show_all()

    @classmethod
    def on_quit(cls, _):
        Gtk.main_quit()
        sys.exit(0)

    def update_tray_icon(self, color):
        # Map color names to valid RGB values
        color_mapping = {
            "blue": "blue",
            "green": "green",
            "yellow": "yellow",
            "red": "red",
        }

        # Generate the dot icon for the given color (fallback if invalid color)
        rgb_color = color_mapping.get(color, "gray")  # Default to gray for invalid colors
        icon_path = self.generate_dot_icon(rgb_color)

        # Set the tray's icon using the generated dot image
        self.indicator.set_icon_full(icon_path, color)

    @classmethod
    def calculate_trend_arrow(cls, data_points):
        # Calculate the rate of change mmol/L per 5 mins and assign arrow
        # Use last 2 points if available
        if len(data_points) < 2:
            return "→"
        v1 = data_points[-2][1]
        v2 = data_points[-1][1]
        delta = v2 - v1
        rate = delta / 5  # mmol/L per minute approx

        if rate >= 0.1:
            return "↑↑"
        elif rate >= 0.03:
            return "↑"
        elif rate <= -0.1:
            return "↓↓"
        elif rate <= -0.03:
            return "↓"
        else:
            return "→"

    @classmethod
    def notify(cls, title, message):
        n = notify2.Notification(title, message)
        n.set_urgency(notify2.URGENCY_NORMAL)
        n.show()

    def check_alerts(self, glucose_val):
        if glucose_val < self.LOW_THRESHOLD and not self.low_alerted:
            self.notify("Low Glucose Alert", f"Glucose low: {glucose_val:.1f} mmol/L")
            self.low_alerted = True
            self.high_alerted = False
        elif glucose_val > self.HIGH_THRESHOLD and not self.high_alerted:
            self.notify("High Glucose Alert", f"Glucose high: {glucose_val:.1f} mmol/L")
            self.high_alerted = True
            self.low_alerted = False
        elif self.LOW_THRESHOLD <= glucose_val <= self.HIGH_THRESHOLD:
            # reset alerts
            self.low_alerted = False
            self.high_alerted = False

    def glucose_color(self, glucose_val):
        if glucose_val < self.LOW_THRESHOLD or glucose_val > self.HIGH_THRESHOLD:
            return "red"
        elif glucose_val < self.NORMAL_THRESHOLD_MIN:
            return "yellow"
        elif glucose_val > self.NORMAL_THRESHOLD_MAX:
            return "yellow"
        else:
            return "green"

    def update_tray(self):
        if self.current_glucose is None:
            self.indicator.set_label("---", "No data available")
            self.update_tray_icon("blue")
            return

        # Set tray label and icon color based on glucose levels
        self.indicator.set_label(f"{self.trend_arrow} {self.current_glucose:.1f} mmol/L",
                                 f"{self.current_glucose:.1f} mmol/L")
        color = self.glucose_color(self.current_glucose)
        self.update_tray_icon(color)
        print(f"[Tray] Updated with glucose value: {self.current_glucose}, trend: {self.trend_arrow}, color: {color}")

    def load_events(self):
        # Load last 24h glucose data from API
        now = datetime.datetime.now(datetime.timezone.utc)
        from_dt = now - datetime.timedelta(hours=24)
        glucose_data = self.client.fetch_glucose_data(from_dt, now)
        if glucose_data:
            # Parse glucose points: adapt if API returns differently, here assuming list of events in glucose_data
            # We'll expect glucose_data to be a list of dicts with 'EventDate' and 'convertedValue'
            readings = []
            for event in glucose_data:
                try:
                    ts = event.get("EventDate")
                    val = event.get("convertedValue")
                    if ts and val is not None:
                        # Convert timestamp string to ISO format (remove timezone info if present)
                        if ts.endswith("Z"):
                            ts = ts[:-1]
                        # Some timestamps might have timezone, ensure isoformat without tz for DB
                        dt = datetime.datetime.fromisoformat(ts)
                        readings.append((dt.isoformat(), float(val)))
                except Exception as e:
                    print(f"[Parse] Error parsing event: {e}")
            if readings:
                self.db.add_readings(readings)
                self.db.prune_old()
                last_points = self.db.get_last_24h()
                if last_points:
                    self.current_glucose = last_points[-1][1]
                    self.trend_arrow = self.calculate_trend_arrow(last_points)
                    self.check_alerts(self.current_glucose)
                    GLib.idle_add(self.update_tray)

    def fetch_loop(self):
        while True:
            try:
                # Login + get user id if missing
                if not self.client.access_token or self.user_id is None:
                    if not self.client.login():
                        print("[FetchLoop] Login failed, retrying in 60s")
                        time.sleep(60)
                        continue
                    self.user_id = self.client.fetch_user_id()
                    if self.user_id is None:
                        print("[FetchLoop] Failed to get user ID, retrying in 60s")
                        time.sleep(60)
                        continue
                    self.client.user_id = self.user_id

                self.load_events()

            except Exception as e:
                print(f"[FetchLoop] Error: {e}")
            # Sleep with jitter
            time.sleep(self.FETCH_INTERVAL_SEC + random.uniform(-30, 30))

    def create_graph_window(self):
        window = Gtk.Window(title="Eversense 24h Glucose")
        window.set_default_size(800, 400)

        data = self.db.get_last_24h()
        if not data:
            label = Gtk.Label(label="No glucose data available")
            window.add(label)
            return window

        times = [x[0].replace(tzinfo=None) for x in data]
        values = [x[1] for x in data]

        max_y = math.ceil(max(values))

        df = pd.DataFrame(sorted(zip(times, values)), columns=["time", "value"])
        df.set_index("time", inplace=True)

        df = df.resample("5min").mean().interpolate()

        # Now plot
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.plot(df.index, df["value"], color="blue", linestyle="-")

        ax.yaxis.grid(True, linestyle=":", color="gray")
        ax.xaxis.grid(True, linestyle=":", color="gray")

        ax.set_title("Last 24 Hours Glucose (mmol/L)")
        ax.set_ylabel("Glucose (mmol/L)")
        ax.set_ylim(0, max_y)
        ax.set_yticks(range(2, max_y + 1, 2))  # Labels every 2 units starting from 2

        ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m - %H:%M'))
        fig.autofmt_xdate()

        # Convert matplotlib figure to GTK Pixbuf
        import io
        from PIL import Image

        buf = io.BytesIO()
        fig.savefig(buf, format='png')
        buf.seek(0)
        pil_im = Image.open(buf)
        width, height = pil_im.size
        pil_im = pil_im.convert("RGBA")
        data = pil_im.tobytes()
        pixbuf = GdkPixbuf.Pixbuf.new_from_data(data, GdkPixbuf.Colorspace.RGB, True, 8, width, height, width * 4)
        image = Gtk.Image.new_from_pixbuf(pixbuf)

        window.add(image)
        return window

    def run(self):
        self.setup_tray()
        self.fetch_thread = threading.Thread(target=self.fetch_loop, daemon=True)
        self.fetch_thread.start()
        Gtk.main()
