import os
import re
import time

from jnius import autoclass, PythonJavaClass, java_method


class CallbackRunnable(PythonJavaClass):
    __javainterfaces__ = ["java/lang/Runnable"]

    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    @java_method("()V")
    def run(self):
        self.callback()


class RecognitionListener(PythonJavaClass):
    __javainterfaces__ = ["android/speech/RecognitionListener"]

    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    @java_method("(Landroid/os/Bundle;)V")
    def onReadyForSpeech(self, params):
        self.owner.notify_app("STATUS|LISTENING — say JARVIS")

    @java_method("()V")
    def onBeginningOfSpeech(self):
        self.owner.notify_app("STATUS|HEARING YOU...")

    @java_method("([F)V")
    def onRmsChanged(self, rmsdB):
        pass

    @java_method("([B)V")
    def onBufferReceived(self, buffer):
        pass

    @java_method("()V")
    def onEndOfSpeech(self):
        pass

    @java_method("(I)V")
    def onError(self, error):
        self.owner.on_error(error)

    @java_method("(Landroid/os/Bundle;)V")
    def onResults(self, results):
        self.owner.on_results(results)

    @java_method("(Landroid/os/Bundle;)V")
    def onPartialResults(self, results):
        self.owner.on_partial(results)

    @java_method("(ILandroid/os/Bundle;)V")
    def onEvent(self, eventType, params):
        pass

    @java_method("(Landroid/os/Bundle;)V")
    def onLanguageDetection(self, results):
        pass


class TTSListener(PythonJavaClass):
    __javainterfaces__ = ["android/speech/tts/TextToSpeech$OnInitListener"]

    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    @java_method("(I)V")
    def onInit(self, status):
        self.owner.tts_ready = (status == 0)
        if self.owner.tts_ready:
            self.owner.speak("JARVIS voice system online.")


class VoiceService:
    def __init__(self):
        self.Intent = autoclass("android.content.Intent")
        self.RecognizerIntent = autoclass("android.speech.RecognizerIntent")
        self.SpeechRecognizer = autoclass("android.speech.SpeechRecognizer")
        self.PythonService = autoclass("org.kivy.android.PythonService")
        self.TTS = autoclass("android.speech.tts.TextToSpeech")
        self.Handler = autoclass("android.os.Handler")
        self.Looper = autoclass("android.os.Looper")
        self.ArrayList = autoclass("java.util.ArrayList")

        self.context = self.PythonService.mService
        self.handler = self.Handler(self.Looper.getMainLooper())
        self.listener = RecognitionListener(self)
        self.tts_listener = TTSListener(self)

        self.recognizer = None
        self.tts = None
        self.tts_ready = False
        self.active = True
        self.awake = False
        self.restart_pending = False
        self.last_text = ""

        self.files_dir = str(self.context.getFilesDir().getAbsolutePath())
        self.event_file = os.path.join(self.files_dir, "jarvis_voice_events.txt")

        self.notify_app("STATUS|SERVICE STARTING")
        self.tts = self.TTS(self.context, self.tts_listener)
        self.post(self.start_listening, 800)

    def post(self, callback, delay_ms=0):
        runnable = CallbackRunnable(callback)
        if not hasattr(self, "_runnables"):
            self._runnables = []
        self._runnables.append(runnable)

        def wrapped():
            try:
                callback()
            finally:
                try:
                    self._runnables.remove(runnable)
                except Exception:
                    pass

        runnable.callback = wrapped
        if delay_ms:
            self.handler.postDelayed(runnable, delay_ms)
        else:
            self.handler.post(runnable)

    def notify_app(self, event):
        try:
            with open(self.event_file, "a", encoding="utf-8") as f:
                f.write(event.replace("\n", " ") + "\n")
        except Exception:
            pass

    def speak(self, text, queue=False):
        try:
            if self.tts is not None and self.tts_ready:
                mode = self.TTS.QUEUE_ADD if queue else self.TTS.QUEUE_FLUSH
                self.tts.speak(
                    text, mode, None,
                    "jarvis_" + str(int(time.time() * 1000))
                )
        except Exception as e:
            self.notify_app("ERROR|TTS: " + str(e))

    def make_intent(self):
        intent = self.Intent(self.RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
        intent.putExtra(
            self.RecognizerIntent.EXTRA_LANGUAGE_MODEL,
            self.RecognizerIntent.LANGUAGE_MODEL_FREE_FORM
        )
        intent.putExtra(self.RecognizerIntent.EXTRA_PARTIAL_RESULTS, True)
        intent.putExtra(self.RecognizerIntent.EXTRA_MAX_RESULTS, 3)
        # Start with the broadly supported Indian English locale.
        # Android's recognizer can still return Hindi on devices/services
        # configured for Hindi; language switching is added when supported.
        intent.putExtra(self.RecognizerIntent.EXTRA_LANGUAGE, "en-IN")

        try:
            allowed = self.ArrayList()
            allowed.add("en-IN")
            allowed.add("hi-IN")
            intent.putExtra(
                self.RecognizerIntent.EXTRA_ENABLE_LANGUAGE_DETECTION, True
            )
            intent.putExtra(
                self.RecognizerIntent.EXTRA_ENABLE_LANGUAGE_SWITCH,
                self.RecognizerIntent.LANGUAGE_SWITCH_BALANCED
            )
            intent.putExtra(
                self.RecognizerIntent.EXTRA_LANGUAGE_DETECTION_ALLOWED_LANGUAGES,
                allowed
            )
            intent.putExtra(
                self.RecognizerIntent.EXTRA_LANGUAGE_SWITCH_ALLOWED_LANGUAGES,
                allowed
            )
        except Exception:
            pass
        return intent

    def start_listening(self):
        if not self.active:
            return
        self.restart_pending = False

        try:
            if not self.SpeechRecognizer.isRecognitionAvailable(self.context):
                self.notify_app(
                    "ERROR|Speech recognition service is not available on this phone."
                )
                self.schedule_restart(5000)
                return

            if self.recognizer is not None:
                try:
                    self.recognizer.cancel()
                    self.recognizer.destroy()
                except Exception:
                    pass
                self.recognizer = None

            self.recognizer = self.SpeechRecognizer.createSpeechRecognizer(
                self.context
            )
            self.recognizer.setRecognitionListener(self.listener)
            self.recognizer.startListening(self.make_intent())
            self.notify_app("STATUS|LISTENING — say JARVIS")
        except Exception as e:
            self.recognizer = None
            self.notify_app("ERROR|Recognizer start: " + str(e))
            self.schedule_restart(2500)

    def schedule_restart(self, delay_ms=1000):
        if not self.active or self.restart_pending:
            return
        self.restart_pending = True
        self.post(self.start_listening, delay_ms)

    def on_partial(self, results):
        try:
            arr = results.getStringArrayList(
                self.SpeechRecognizer.RESULTS_RECOGNITION
            )
            if arr and arr.size() > 0:
                text = str(arr.get(0))
                self.process_text(text, True)
        except Exception:
            pass

    def on_results(self, results):
        try:
            arr = results.getStringArrayList(
                self.SpeechRecognizer.RESULTS_RECOGNITION
            )
            if arr and arr.size() > 0:
                self.process_text(str(arr.get(0)), False)
            else:
                self.schedule_restart(700)
        except Exception:
            self.schedule_restart(1000)

    def on_error(self, error):
        # ERROR_NO_MATCH (7) is normal while waiting for a wake word.
        if error == 7:
            self.notify_app("STATUS|LISTENING — say JARVIS")
            self.schedule_restart(400)
            return
        names = {
            1: "network error", 2: "network timeout", 3: "audio error",
            4: "server error", 5: "client error", 6: "speech timeout",
            8: "recognizer busy", 9: "insufficient permissions",
            10: "language unavailable", 11: "language not supported",
            12: "server disconnected", 13: "cannot listen while in call"
        }
        self.notify_app("ERROR|SpeechRecognizer " + str(error) + ": " + names.get(error, "unknown error"))
        self.schedule_restart(1500)

    def process_text(self, text, partial=False):
        text = re.sub(r"\s+", " ", text.strip())
        if not text:
            return

        # Do not wait for a separate UI event: recognize the wake word first.
        # Final results such as "Jarvis" or "Jarvis help" are the primary path.
        if self.contains_wake(text):
            remainder = self.remove_wake(text)
            if not self.awake:
                self.activate_wake(text)
                if remainder.strip():
                    # Keep the acknowledgement and command response in order.
                    self.post(lambda: self.execute_command(remainder.strip()), 1500)
                return

        if partial:
            self.notify_app("PARTIAL|" + text)
            return

        self.notify_app("HEARD|" + text)

        if not self.awake:
            return

        self.awake = False
        low = text.lower()
        if low in {"cancel", "stop", "never mind", "नहीं", "रहने दो"}:
            self.speak("Okay Boss.", queue=False)
            self.schedule_restart(700)
            return

        self.execute_command(text)

    @staticmethod
    def normalize_voice_text(text):
        text = text.lower().strip()
        text = text.replace("jar vis", "jarvis")
        text = text.replace("jaarvis", "jarvis")
        text = text.replace("jarvish", "jarvis")
        text = re.sub(r"[^a-z0-9\u0900-\u097f]+", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    @classmethod
    def contains_wake(cls, text):
        normalized = cls.normalize_voice_text(text)
        return "jarvis" in normalized or "जार्विस" in normalized

    @classmethod
    def remove_wake(cls, text):
        cleaned = re.sub(r"(?i)jar\s*vis", "", text)
        cleaned = re.sub(r"(?i)jaar\s*vis", "", cleaned)
        cleaned = re.sub(r"(?i)jarvish", "", cleaned)
        cleaned = cleaned.replace("जार्विस", "")
        return re.sub(r"\s+", " ", cleaned).strip()

    def activate_wake(self, original):
        if self.awake:
            return
        self.awake = True
        try:
            if self.recognizer is not None:
                self.recognizer.cancel()
                self.recognizer.destroy()
        except Exception:
            pass
        self.recognizer = None
        self.notify_app("WAKE|" + original)
        self.speak("Yes Boss. How can I help you?", queue=False)
        self.post(self.start_listening, 1800)

    def execute_command(self, command):
        try:
            from jarvis_core import JarvisCore
            data_file = os.path.join(self.files_dir, "jarvis_data.json")
            response = JarvisCore(data_file).handle(command)
            self.notify_app("COMMAND|" + command)
            self.speak(self.clean_for_speech(response), queue=True)
        except Exception as e:
            self.notify_app("ERROR|Command: " + str(e))
            self.speak("Sorry Boss, I could not process that command.")
        finally:
            self.awake = False
            self.schedule_restart(1000)

    @staticmethod
    def clean_for_speech(text):
        text = text.replace("[DONE]", "done").replace("[ ]", "")
        text = re.sub(r"\s+", " ", text)
        return text[:500] + ("." if len(text) > 500 else "")


def main():
    service = VoiceService()
    try:
        while service.active:
            time.sleep(1)
    except KeyboardInterrupt:
        service.active = False


if __name__ == "__main__":
    main()
