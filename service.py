import os
import time
from jnius import autoclass

from jarvis_core import JarvisCore
from main import VoiceEngine


class ServiceApp:
    def __init__(self):
        self.activity = autoclass("org.kivy.android.PythonService").mService
        self.files_dir = str(self.activity.getFilesDir().getAbsolutePath())
        self.data_file = os.path.join(self.files_dir, "jarvis_data.json")
        self.core = JarvisCore(self.data_file)
        self.event_file = os.path.join(self.files_dir, "jarvis_voice_events.txt")

    def show_voice(self, text):
        try:
            with open(self.event_file, "a", encoding="utf-8") as f:
                f.write("EVENT|" + str(text).replace("\n", " ") + "\n")
        except Exception:
            pass


def main():
    app = ServiceApp()
    engine = VoiceEngine(app)
    engine.start()
    try:
        while not engine.destroyed:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            engine.shutdown()
        except Exception:
            pass


if __name__ == "__main__":
    main()
