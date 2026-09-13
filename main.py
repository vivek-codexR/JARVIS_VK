import os
import re
import time
import difflib
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


class RecognitionListener(__import__('jnius').PythonJavaClass):
    __javainterfaces__ = ["android/speech/RecognitionListener"]

    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    @__import__('jnius').java_method("(Landroid/os/Bundle;)V")
    def onReadyForSpeech(self, params):
        self.owner.voice_status("LISTENING — say VYRo")

    @__import__('jnius').java_method("()V")
    def onBeginningOfSpeech(self):
        self.owner.voice_status("HEARING YOU...")

    @__import__('jnius').java_method("([F)V")
    def onRmsChanged(self, rms):
        pass

    @__import__('jnius').java_method("([B)V")
    def onBufferReceived(self, buffer):
        pass

    @__import__('jnius').java_method("()V")
    def onEndOfSpeech(self):
        pass

    @__import__('jnius').java_method("(I)V")
    def onError(self, error):
        self.owner.voice_error(error)

    @__import__('jnius').java_method("(Landroid/os/Bundle;)V")
    def onResults(self, results):
        self.owner.voice_results(results)

    @__import__('jnius').java_method("(Landroid/os/Bundle;)V")
    def onPartialResults(self, results):
        self.owner.voice_partial(results)

    @__import__('jnius').java_method("(ILandroid/os/Bundle;)V")
    def onEvent(self, eventType, params):
        pass


class TTSInitListener(__import__('jnius').PythonJavaClass):
    __javainterfaces__ = ["android/speech/tts/TextToSpeech$OnInitListener"]

    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    @__import__('jnius').java_method("(I)V")
    def onInit(self, status):
        self.owner.tts_initialized(status)


class VoiceEngine:
    """Voice engine with one hard rule: every SpeechRecognizer operation is
    posted to Android's main application looper.

    RecognitionListener callbacks can arrive from a binder/service thread, so
    we NEVER call SpeechRecognizer.cancel/destroy/startListening directly from
    those callbacks.
    """

    def __init__(self, app):
        self.app = app
        self.J = __import__('jnius')
        autoclass = self.J.autoclass
        self.Intent = autoclass("android.content.Intent")
        self.RecognizerIntent = autoclass("android.speech.RecognizerIntent")
        self.SpeechRecognizer = autoclass("android.speech.SpeechRecognizer")
        self.TTS = autoclass("android.speech.tts.TextToSpeech")
        self.Locale = autoclass("java.util.Locale")
        self.ArrayList = autoclass("java.util.ArrayList")
        self.AudioAttributesBuilder = autoclass("android.media.AudioAttributes$Builder")
        self.Handler = autoclass("android.os.Handler")
        self.Looper = autoclass("android.os.Looper")

        # Android SpeechRecognizer requires its API methods to run on the
        # application's main thread. This handler is our single gatekeeper.
        self.main_handler = self.Handler(self.Looper.getMainLooper())

        self.recognizer = None
        self.listener = RecognitionListener(self)
        self.tts = None
        self.tts_init_listener = TTSInitListener(self)
        self.tts_ready = False
        self.language_ok = False
        self.awake = False
        self.last_wake = 0.0
        self.starting = False
        self.destroyed = False
        self.last_command_at = 0.0
        self.command_cooldown = 0.8

    class MainRunnable(__import__('jnius').PythonJavaClass):
        __javainterfaces__ = ["java/lang/Runnable"]

        def __init__(self, fn):
            super().__init__()
            self.fn = fn

        @__import__('jnius').java_method("()V")
        def run(self):
            try:
                self.fn()
            except Exception as e:
                # Do not let a Java-main-thread callback kill the recognizer.
                try:
                    self.fn_error(e)
                except Exception:
                    pass

    def post_main(self, fn, delay_ms=0):
        runnable = self.MainRunnable(fn)
        # Keep a Python reference alive until Java has executed the Runnable.
        if not hasattr(self, "_runnables"):
            self._runnables = []
        self._runnables.append(runnable)

        def cleanup_run():
            try:
                fn()
            except Exception as e:
                self.ui("Main-thread error: " + str(e))
            finally:
                try:
                    self._runnables.remove(runnable)
                except Exception:
                    pass
        # Replace callback target used by run().
        runnable.fn = cleanup_run
        try:
            if delay_ms:
                self.main_handler.postDelayed(runnable, int(delay_ms))
            else:
                self.main_handler.post(runnable)
        except Exception:
            try:
                self._runnables.remove(runnable)
            except Exception:
                pass

    def ui(self, text):
        # Kivy UI updates belong on Kivy's event loop, not a recognizer binder
        # callback thread.
        try:
            Clock.schedule_once(lambda *_: self.app.show_voice(str(text)), 0)
        except Exception:
            pass

    def start(self):
        try:
            if not self.SpeechRecognizer.isRecognitionAvailable(self.app.activity):
                self.ui("Speech recognition is NOT available on this phone.")
                return
            self.ui("Voice engine starting...")
            self.post_main(self.init_tts, 100)
            self.post_main(self.start_recognition, 700)
        except Exception as e:
            self.ui("Voice start error: " + str(e))

    # ---------------- TTS ----------------
    def init_tts(self):
        try:
            if self.tts is None:
                self.tts = self.TTS(self.app.activity, self.tts_init_listener)
        except Exception as e:
            self.ui("TTS creation error: " + str(e))

    def tts_initialized(self, status):
        # TTS init callback may not be the Kivy thread. Keep Android calls
        # serialized on the main looper too.
        self.post_main(lambda: self._tts_initialized_main(status), 0)

    def _tts_initialized_main(self, status):
        if status != self.TTS.SUCCESS:
            self.ui("TTS initialization failed: " + str(status))
            return
        try:
            result = self.tts.setLanguage(self.Locale("en", "IN"))
            if result in (self.TTS.LANG_MISSING_DATA, self.TTS.LANG_NOT_SUPPORTED):
                result = self.tts.setLanguage(self.Locale.US)
            self.language_ok = result not in (
                self.TTS.LANG_MISSING_DATA,
                self.TTS.LANG_NOT_SUPPORTED,
            )
            try:
                attrs = (self.AudioAttributesBuilder()
                         .setUsage(1)
                         .setContentType(1)
                         .build())
                self.tts.setAudioAttributes(attrs)
            except Exception:
                pass
            self.tts_ready = self.language_ok
            self.ui("TTS READY • language=" + str(result))
            if self.tts_ready:
                self.post_main(lambda: self.speak("VYRo voice system online."), 250)
        except Exception as e:
            self.ui("TTS setup error: " + str(e))

    def speak(self, text):
        # speak() itself is always posted to Android main looper.
        self.post_main(lambda: self._speak_main(str(text)), 0)

    def _speak_main(self, text):
        if not self.tts_ready or self.tts is None:
            self.ui("TTS not ready")
            return
        try:
            # Use the stable 3-argument TextToSpeech overload here.
            # The 4-argument utterance-ID overload was producing a PyJNIus
            # argument/overload exception on the target Android build.
            result = self.tts.speak(str(text), self.TTS.QUEUE_FLUSH, None)
            if result == self.TTS.SUCCESS:
                self.ui("TTS ACCEPTED • audio requested")
            else:
                self.ui("TTS REJECTED • code=" + str(result))
        except Exception as e:
            self.ui("TTS speak error: " + str(e))

    # ---------------- Speech recognition ----------------
    def make_intent(self):
        intent = self.Intent(self.RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
        intent.putExtra(self.RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                        self.RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
        intent.putExtra(self.RecognizerIntent.EXTRA_PARTIAL_RESULTS, True)
        intent.putExtra(self.RecognizerIntent.EXTRA_MAX_RESULTS, 5)
        intent.putExtra(self.RecognizerIntent.EXTRA_LANGUAGE, "en-IN")
        try:
            allowed = self.ArrayList()
            allowed.add("en-IN")
            allowed.add("hi-IN")
            intent.putExtra(self.RecognizerIntent.EXTRA_ENABLE_LANGUAGE_DETECTION, True)
            intent.putExtra(self.RecognizerIntent.EXTRA_LANGUAGE_DETECTION_ALLOWED_LANGUAGES, allowed)
            intent.putExtra(self.RecognizerIntent.EXTRA_ENABLE_LANGUAGE_SWITCH,
                            self.RecognizerIntent.LANGUAGE_SWITCH_BALANCED)
            intent.putExtra(self.RecognizerIntent.EXTRA_LANGUAGE_SWITCH_ALLOWED_LANGUAGES, allowed)
        except Exception:
            # Older recognition providers may not support API 34 language switch extras.
            pass
        return intent

    def start_recognition(self):
        # THIS METHOD MUST ONLY BE ENTERED VIA post_main().
        if self.destroyed or self.starting:
            return
        self.starting = True
        try:
            if self.recognizer is not None:
                try:
                    self.recognizer.cancel()
                except Exception:
                    pass
                try:
                    self.recognizer.destroy()
                except Exception:
                    pass
                self.recognizer = None

            self.recognizer = self.SpeechRecognizer.createSpeechRecognizer(self.app.activity)
            self.recognizer.setRecognitionListener(self.listener)
            self.recognizer.startListening(self.make_intent())
            self.ui("LISTENING • say VYRo")
        except Exception as e:
            self.ui("Recognizer error: " + str(e))
            self.post_main(self.start_recognition, 1500)
        finally:
            self.starting = False

    def cancel_recognition(self):
        def work():
            try:
                if self.recognizer is not None:
                    self.recognizer.cancel()
            except Exception:
                pass
        self.post_main(work, 0)

    @staticmethod
    def normalize(text):
        text = str(text).lower().strip()
        replacements = {
            "vy ro": "vyro", "v y ro": "vyro", "vairo": "vyro", "viro": "vyro",
            "vyrah": "vyro", "वायरो": "vyro", "वाय रो": "vyro",
        }
        for a, b in replacements.items():
            text = text.replace(a, b)
        return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text)).strip()

    @classmethod
    def has_wake(cls, text):
        n = cls.normalize(text)
        if "vyro" in n:
            return True
        for token in n.split():
            if len(token) >= 3 and difflib.SequenceMatcher(None, token, "vyro").ratio() >= 0.72:
                return True
        return False

    @classmethod
    def remove_wake(cls, text):
        text = re.sub(r"(?i)v\s*y\s*r\s*o", "", str(text))
        text = re.sub(r"(?i)vyro|vairo|viro|vyrah", "", text)
        text = text.replace("वायरो", "")
        return re.sub(r"\s+", " ", text).strip(" ,.!?")

    def extract(self, bundle):
        arr = bundle.getStringArrayList(self.SpeechRecognizer.RESULTS_RECOGNITION)
        if not arr or arr.size() == 0:
            return []
        return [str(arr.get(i)) for i in range(min(arr.size(), 5))]

    # Listener callbacks can arrive off the main thread. We only read the
    # Bundle here and post any recognizer/UI work back to the proper loops.
    def voice_partial(self, results):
        try:
            items = self.extract(results)
            if items:
                text = items[0]
                self.ui("Hearing: " + text)
                if self.has_wake(text):
                    self.post_main(lambda t=text: self.handle_wake(t), 0)
        except Exception as e:
            self.ui("Partial result error: " + str(e))

    def voice_results(self, results):
        try:
            items = self.extract(results)
            if not items:
                self.post_main(self.start_recognition, 400)
                return
            for text in items:
                if self.has_wake(text):
                    self.post_main(lambda t=text: self.handle_wake(t), 0)
                    return
            self.ui("Heard: " + items[0])
            if self.awake:
                self.post_main(lambda t=items[0]: self.handle_command(t), 0)
            else:
                self.post_main(self.start_recognition, 400)
        except Exception as e:
            self.ui("Result error: " + str(e))
            self.post_main(self.start_recognition, 1000)

    def voice_error(self, error):
        names = {1:"network",2:"network timeout",3:"audio",4:"server",5:"client",
                 6:"speech timeout",7:"no match",8:"busy",9:"permission",
                 10:"language unavailable",11:"language unsupported"}
        self.ui("Recognizer: " + names.get(error, "error") + " (" + str(error) + ")")
        self.post_main(self.start_recognition, 500 if error == 7 else 1500)

    def handle_wake(self, original):
        now = time.time()
        if now - self.last_wake < 1.2:
            return
        self.last_wake = now
        self.awake = True
        remainder = self.remove_wake(original)
        self.cancel_recognition()
        self.ui("✅ VYRo AWAKE\n\n" + original)
        self.speak("Yes Boss. How can I help you?")
        if remainder:
            self.post_main(lambda r=remainder: self.handle_command(r), 1900)
        else:
            self.post_main(self.start_recognition, 1900)

    def handle_command(self, command):
        if not self.awake:
            return
        now = time.time()
        if now - self.last_command_at < self.command_cooldown:
            return
        self.last_command_at = now
        self.awake = False
        try:
            response = self.app.core.handle(command)
            self.ui("Command: " + command + "\n\n" + response)
            self.speak(re.sub(r"\s+", " ", str(response)))
        except Exception as e:
            self.ui("Command error: " + str(e))
            self.speak("Sorry Boss, I could not process that command.")
        self.post_main(self.start_recognition, 1300)

    def restart_voice(self):
        if self.destroyed:
            return
        self.awake = False
        self.ui("RESTARTING VYRo V1.7...")
        self.cancel_recognition()
        self.post_main(self.start_recognition, 500)

    def shutdown(self):
        self.destroyed = True
        def work():
            try:
                if self.recognizer is not None:
                    self.recognizer.cancel()
                    self.recognizer.destroy()
                    self.recognizer = None
            except Exception:
                pass
            try:
                if self.tts is not None:
                    self.tts.stop()
                    self.tts.shutdown()
                    self.tts = None
            except Exception:
                pass
        self.post_main(work, 0)


class VyroApp(App):
    def build(self):
        self.title = "VYRo V1.7"
        self.activity = __import__('jnius').autoclass("org.kivy.android.PythonActivity").mActivity
        self.app_files_dir = str(self.activity.getFilesDir().getAbsolutePath())
        self.data_file = os.path.join(self.app_files_dir, "jarvis_data.json")
        self.core = JarvisCore(self.data_file)
        self.voice = None

        root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        root.add_widget(Label(text="VYRo V1.7\nYour Personal AI Assistant", font_size=dp(24), size_hint_y=None, height=dp(90)))
        self.status = Label(text="STARTING VYRo V1.7...", size_hint_y=None, height=dp(35))
        root.add_widget(self.status)
        self.output = Label(text="Welcome Boss.\n\nVYRo V1.7 voice engine starting...", halign="left", valign="top", size_hint_y=None)
        self.output.bind(texture_size=lambda *_: setattr(self.output, "height", self.output.texture_size[1] + dp(20)))
        scroll = ScrollView(); scroll.add_widget(self.output); root.add_widget(scroll)

        self.command = TextInput(hint_text="Type a command...", multiline=False, size_hint_y=None, height=dp(50))
        self.command.bind(on_text_validate=lambda *_: self.run_command())
        root.add_widget(self.command)
        row = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(6))
        for text, cmd in [("Rules","rules"),("Timetable","timetable"),("Tasks","tasks"),("Summary","summary")]:
            b=Button(text=text); b.bind(on_press=lambda _, c=cmd: self.handle(c)); row.add_widget(b)
        root.add_widget(row)
        send=Button(text="RUN COMMAND", size_hint_y=None, height=dp(55)); send.bind(on_press=lambda *_: self.run_command()); root.add_widget(send)
        restart=Button(text="RESTART VOICE", size_hint_y=None, height=dp(48)); restart.bind(on_press=lambda *_: self.voice.restart_voice() if self.voice else None); root.add_widget(restart)

        self.request_voice_permission()
        return root

    def request_voice_permission(self):
        def after(*_):
            try:
                self.voice = VoiceEngine(self)
                self.voice.start()
            except Exception as e:
                self.show_voice("Voice engine error: " + str(e))
        try:
            from android.permissions import request_permissions
            request_permissions(["android.permission.RECORD_AUDIO"], after)
        except Exception:
            after()

    def show_voice(self, text):
        self.status.text = "ONLINE • VYRo VOICE ACTIVE"
        self.output.text = str(text)

    def run_command(self):
        text=self.command.text.strip(); self.command.text=""
        if text: self.handle(text)

    def handle(self, command):
        self.output.text=self.core.handle(command)

    def on_stop(self):
        try:
            if self.voice:
                self.voice.shutdown()
        except Exception:
            pass
        return super().on_stop()


if __name__ == "__main__":
    VyroApp().run()
