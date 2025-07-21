import logging
import re

import gi  # type: ignore

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # type: ignore


class LoginDialog(Gtk.Dialog):
    EMAIL_REGEX = re.compile(r"^[^@]+@[^@]+\.[^@]+$")

    def __init__(self, parent=None):
        super().__init__(title="Eversense Tray Login", transient_for=parent, flags=0)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.set_modal(True)
        self.set_default_size(300, 100)

        self.set_modal(True)
        self.set_default_size(300, 120)
        self.set_border_width(10)

        self.set_resizable(False)

        box = self.get_content_area()

        self.username_entry = Gtk.Entry()
        self.username_entry.set_placeholder_text("Email address")
        self.username_entry.connect("changed", self.on_input_changed)
        box.add(self.username_entry)

        self.password_entry = Gtk.Entry()
        self.password_entry.set_placeholder_text("Password")
        self.password_entry.set_visibility(False)
        self.password_entry.connect("changed", self.on_input_changed)
        box.add(self.password_entry)

        self.error_label = Gtk.Label(label="")
        self.error_label.set_halign(Gtk.Align.START)
        self.error_label.set_valign(Gtk.Align.START)
        self.error_label.set_use_markup(True)
        box.add(self.error_label)

        self.cancel_button = self.add_button("Cancel", Gtk.ResponseType.CANCEL)
        self.login_button = self.add_button("Login", Gtk.ResponseType.OK)
        self.login_button.set_sensitive(False)

        self.logger.debug("[Dialog] Initialized")
        self.show_all()

    def on_input_changed(self, widget):
        """Check inputs on any change and enable/disable Login button."""
        if self.is_valid():
            self.login_button.set_sensitive(True)
            self.error_label.set_markup("")
        else:
            self.login_button.set_sensitive(False)

    def is_valid(self):
        """Returns True if current inputs are valid."""
        username = self.username_entry.get_text().strip()
        password = self.password_entry.get_text().strip()
        return bool(self.EMAIL_REGEX.match(username)) and bool(password)

    def run(self):
        """Override to enforce validation before closing with OK."""
        while True:
            response = super().run()
            if response == Gtk.ResponseType.OK:
                if self.is_valid():
                    return response
                else:
                    self.error_label.set_markup(
                        "<span foreground='red'>Please enter a valid email and password.</span>"
                    )
                    continue
            return response

    def get_credentials(self):
        return self.username_entry.get_text(), self.password_entry.get_text()
