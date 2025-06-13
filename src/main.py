import notify2

from app import GlucoseApp

notify2.init("Eversense CGM")


if __name__ == "__main__":
    app = GlucoseApp()
    app.run()
