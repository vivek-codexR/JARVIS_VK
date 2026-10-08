import os
from datetime import datetime
from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.metrics import dp
from jarvis_core import JarvisCore

class VyroApp(App):
    def build(self):
        self.title="VYRo V1.8.1"
        self.core=JarvisCore(os.path.join(self.user_data_dir,"jarvis_data.json"))
        root=BoxLayout(orientation="vertical",padding=dp(10),spacing=dp(7))
        root.add_widget(Label(text="VYRo V1.8.1\nBackground Voice Assistant",font_size=dp(23),size_hint_y=None,height=dp(75)))
        self.status=Label(text="VOICE SERVICE STARTING...",size_hint_y=None,height=dp(32))
        root.add_widget(self.status)
        self.output=Label(text="VYRo is running in background.\nSay: VYRo",halign="left",valign="top",size_hint_y=None)
        self.output.bind(texture_size=lambda *_: setattr(self.output,"height",self.output.texture_size[1]+dp(20)))
        sc=ScrollView(); sc.add_widget(self.output); root.add_widget(sc)
        self.command=TextInput(hint_text="Type a command...",multiline=False,size_hint_y=None,height=dp(48))
        self.command.bind(on_text_validate=lambda *_: self.run_command()); root.add_widget(self.command)
        row=BoxLayout(size_hint_y=None,height=dp(48),spacing=dp(5))
        for label,cmd in [("Rules","rules"),("Timetable","timetable"),("Tasks","tasks"),("Summary","summary")]:
            b=Button(text=label); b.bind(on_press=lambda _,c=cmd:self.handle(c)); row.add_widget(b)
        root.add_widget(row)
        b=Button(text="RUN COMMAND",size_hint_y=None,height=dp(50)); b.bind(on_press=lambda *_:self.run_command()); root.add_widget(b)
        self.request_voice_permission()
        Clock.schedule_interval(self.refresh,1)
        return root

    def request_voice_permission(self):
        def after(*_):
            self.status.text="ONLINE • VYRo BACKGROUND VOICE ACTIVE"
        try:
            from android.permissions import request_permissions
            request_permissions(["android.permission.RECORD_AUDIO"],after)
        except Exception: after()

    def run_command(self):
        c=self.command.text.strip(); self.command.text=""
        if c:self.handle(c)

    def handle(self,c):
        self.output.text=self.core.handle(c)

    def refresh(self,*_):
        self.status.text="ONLINE • " + datetime.now().strftime("%d-%m-%Y  %I:%M %p") + " • BACKGROUND VOICE"

    def on_stop(self):
        # Intentionally do NOT stop the voice service. Android foreground service
        # continues after the activity/UI is closed.
        return

if __name__=="__main__": VyroApp().run()
