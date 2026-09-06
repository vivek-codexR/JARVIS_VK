import os
from datetime import datetime

from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView

from jarvis_core import JarvisCore


class JarvisApp(App):
    def build(self):
        self.title = "JARVIS V1.4"
        self.app_files_dir = self.get_android_files_dir()
        self.data_file = os.path.join(self.app_files_dir, "jarvis_data.json")
        self.event_file = os.path.join(self.app_files_dir, "jarvis_voice_events.txt")
        self.core = JarvisCore(self.data_file)

        root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))

        self.header = Label(
            text="JARVIS V1.4\nYour Personal Assistant",
            font_size=dp(24), size_hint_y=None, height=dp(90)
        )
        root.add_widget(self.header)

        self.status = Label(
            text="STARTING VOICE...",
            size_hint_y=None, height=dp(35)
        )
        root.add_widget(self.status)

        self.output = Label(
            text='Welcome Boss.\n\nStarting microphone listener...',
            halign="left", valign="top", size_hint_y=None
        )
        self.output.bind(texture_size=lambda *_: setattr(
            self.output, "height", self.output.texture_size[1] + dp(20)
        ))
        scroll = ScrollView()
        scroll.add_widget(self.output)
        root.add_widget(scroll)

        self.command = TextInput(
            hint_text="Type a command...", multiline=False,
            size_hint_y=None, height=dp(50)
        )
        self.command.bind(on_text_validate=lambda *_: self.run_command())
        root.add_widget(self.command)

        row = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(6))
        for text, cmd in [
            ("Rules", "rules"), ("Timetable", "timetable"),
            ("Tasks", "tasks"), ("Summary", "summary")
        ]:
            b = Button(text=text)
            b.bind(on_press=lambda _, c=cmd: self.handle(c))
            row.add_widget(b)
        root.add_widget(row)

        send = Button(text="RUN COMMAND", size_hint_y=None, height=dp(55))
        send.bind(on_press=lambda *_: self.run_command())
        root.add_widget(send)

        self.start_voice_service()
        Clock.schedule_interval(self.poll_voice_events, 0.25)
        Clock.schedule_interval(self.update_clock, 30)
        return root

    def get_android_files_dir(self):
        try:
            from jnius import autoclass
            activity = autoclass("org.kivy.android.PythonActivity").mActivity
            return str(activity.getFilesDir().getAbsolutePath())
        except Exception:
            return self.user_data_dir

    def start_voice_service(self):
        def launch_service(*_):
            try:
                from jnius import autoclass
                Service = autoclass("org.jarvis.jarvisassistant.ServiceJarvisvoice")
                activity = autoclass("org.kivy.android.PythonActivity").mActivity
                Service.start(activity, "")
                self.status.text = "ONLINE • VOICE SERVICE STARTED"
            except Exception as e:
                self.status.text = "VOICE SERVICE ERROR"
                self.output.text = "Could not start voice service.\n\n" + str(e)

        try:
            from android.permissions import request_permissions
            request_permissions(
                [
                    "android.permission.RECORD_AUDIO",
                    "android.permission.POST_NOTIFICATIONS"
                ],
                launch_service
            )
        except Exception:
            launch_service()

    def poll_voice_events(self, *_):
        try:
            if not os.path.exists(self.event_file):
                return
            with open(self.event_file, "r", encoding="utf-8") as f:
                events = [x.strip() for x in f.readlines() if x.strip()]
            os.remove(self.event_file)

            for event in events:
                if event.startswith("STATUS|"):
                    self.status.text = "ONLINE • " + event[7:]
                elif event.startswith("ERROR|"):
                    self.status.text = "VOICE ERROR"
                    self.output.text = "Voice error:\n\n" + event[6:]
                elif event.startswith("PARTIAL|"):
                    self.output.text = "Listening...\n\n" + event[8:]
                elif event.startswith("HEARD|"):
                    self.output.text = "I heard:\n\n" + event[6:]
                elif event.startswith("WAKE|"):
                    self.output.text = (
                        "JARVIS AWAKE\n\n"
                        "Yes Boss. How can I help you?"
                    )
                elif event.startswith("COMMAND|"):
                    self.handle(event[8:].strip())
        except Exception:
            pass

    def update_clock(self, *_):
        self.status.text = (
            "ONLINE • VOICE ACTIVE • " +
            datetime.now().strftime("%d-%m-%Y  %I:%M %p")
        )

    def run_command(self):
        text = self.command.text.strip()
        self.command.text = ""
        if text:
            self.handle(text)

    def handle(self, command):
        self.output.text = self.core.handle(command)

    def on_stop(self):
        return super().on_stop()


if __name__ == "__main__":
    JarvisApp().run()
