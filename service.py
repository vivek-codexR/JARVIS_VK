import os
import re
import time
import difflib

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
        self.owner.notify_app("STATUS|LISTENING — say VYRo")

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
        try:
            detected = results.getString("android.speech.extra.LANGUAGE")
            if detected:
                self.owner.notify_app("LANG|" + str(detected))
        except Exception:
            pass


class TTSListener(PythonJavaClass):
    __javainterfaces__ = ["android/speech/tts/TextToSpeech$OnInitListener"]

    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    @java_method("(I)V")
    def onInit(self, status):
        self.owner.tts_init_status = int(status)
        self.owner.tts_ready = (status == self.owner.TTS.SUCCESS)
        if self.owner.tts_ready:
            self.owner.post(self.owner.configure_tts, 150)
        else:
            self.owner.notify_app("TTS_ERROR|Initialization failed: " + str(status))


class UtteranceListener(PythonJavaClass):
    __javainterfaces__ = ["android/speech/tts/UtteranceProgressListener"]

    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    @java_method("(Ljava/lang/String;)V")
    def onStart(self, utteranceId):
        self.owner.notify_app("TTS_PLAYBACK|START id=" + str(utteranceId))

    @java_method("(Ljava/lang/String;)V")
    def onDone(self, utteranceId):
        self.owner.notify_app("TTS_PLAYBACK|DONE id=" + str(utteranceId))

    @java_method("(Ljava/lang/String;)V")
    def onError(self, utteranceId):
        self.owner.notify_app("TTS_ERROR|Playback error id=" + str(utteranceId))

    @java_method("(Ljava/lang/String;I)V")
    def onErrorWithCode(self, utteranceId, errorCode):
        self.owner.notify_app("TTS_ERROR|Playback error code=" + str(errorCode) + " id=" + str(utteranceId))


class VoiceService:
    def __init__(self):
        self.Intent = autoclass("android.content.Intent")
        self.RecognizerIntent = autoclass("android.speech.RecognizerIntent")
        self.SpeechRecognizer = autoclass("android.speech.SpeechRecognizer")
        self.PythonService = autoclass("org.kivy.android.PythonService")
        self.TTS = autoclass("android.speech.tts.TextToSpeech")
        self.Locale = autoclass("java.util.Locale")
        self.Handler = autoclass("android.os.Handler")
        self.Looper = autoclass("android.os.Looper")
        self.ArrayList = autoclass("java.util.ArrayList")

        self.context = self.PythonService.mService
        self.handler = self.Handler(self.Looper.getMainLooper())
        self.listener = RecognitionListener(self)
        self.tts_listener = TTSListener(self)
        self.tts_progress_listener = UtteranceListener(self)
        self.AudioAttributesBuilder = autoclass("android.media.AudioAttributes$Builder")

        self.recognizer = None
        self.tts = None
        self.tts_ready = False
        self.tts_init_status = -999
        self.tts_language_ok = False
        self.active = True
        self.awake = False
        self.restart_pending = False
        self.last_text = ""
        self.last_wake_at = 0.0
        self._runnables = []

        self.files_dir = str(self.context.getFilesDir().getAbsolutePath())
        self.event_file = os.path.join(self.files_dir, "jarvis_voice_events.txt")

        self.notify_app("STATUS|SERVICE STARTING")
        self.notify_app("DEBUG|V1.5 diagnostic voice engine")

        # TextToSpeech is created on Android's main looper. Creating it from
        # the service bootstrap thread can fail on some Android builds.
        self.post(self.init_tts, 100)
        self.post(self.start_listening, 1000)

    def post(self, callback, delay_ms=0):
        runnable = CallbackRunnable(callback)
        self._runnables.append(runnable)

        def wrapped():
            try:
                callback()
            except Exception as e:
                self.notify_app("ERROR|Main-thread callback: " + str(e))
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

    # ---------------- TTS ----------------
    def init_tts(self):
        try:
            if self.tts is not None:
                return
            self.notify_app("TTS|CREATING_ON_MAIN_THREAD")
            self.tts = self.TTS(self.context, self.tts_listener)
            self.notify_app("TTS|OBJECT_CREATED")
            try:
                self.tts.setOnUtteranceProgressListener(self.tts_progress_listener)
                self.notify_app("TTS|PROGRESS_LISTENER_ATTACHED")
            except Exception as e:
                self.notify_app("TTS_ERROR|Progress listener attach: " + str(e))
        except Exception as e:
            self.notify_app("TTS_ERROR|Could not create TTS on main thread: " + str(e))

    def _speak_now(self, text, queue=False):
        if not text:
            return False
        try:
            if self.tts is None:
                self.notify_app("TTS_ERROR|TTS object is null")
                return False
            if not self.tts_ready:
                self.notify_app("TTS_ERROR|TTS not ready (init_status=" + str(self.tts_init_status) + ")")
                return False
            if not self.tts_language_ok:
                self.notify_app("TTS_ERROR|TTS language unavailable")
                return False

            mode = self.TTS.QUEUE_ADD if queue else self.TTS.QUEUE_FLUSH
            utterance_id = "jarvis_" + str(int(time.time() * 1000))
            result = self.tts.speak(
                str(text), mode, None, utterance_id
            )
            if result == self.TTS.SUCCESS:
                self.notify_app("TTS|SPEAK_ACCEPTED result=SUCCESS(0) id=" + utterance_id + " text=" + str(text)[:180])
                return True
            self.notify_app("TTS_ERROR|SPEAK_REJECTED result=" + str(result) + " id=" + utterance_id + " text=" + str(text)[:180])
            return False
        except Exception as e:
            self.notify_app("TTS_ERROR|speak(main): " + str(e))
            return False

    def configure_tts(self):
        if not self.tts:
            return
        try:
            # Prefer Indian English; fall back to US English if necessary.
            result = self.tts.setLanguage(self.Locale("en", "IN"))
            if result in (self.TTS.LANG_MISSING_DATA, self.TTS.LANG_NOT_SUPPORTED):
                result = self.tts.setLanguage(self.Locale.US)
            self.tts_language_ok = result not in (
                self.TTS.LANG_MISSING_DATA,
                self.TTS.LANG_NOT_SUPPORTED,
            )

            # Make the speech stream explicit so Android routes VYRo voice
            # through a normal audible media/speech path.
            try:
                attrs = (self.AudioAttributesBuilder()
                         .setUsage(1)
                         .setContentType(1)
                         .build())
                audio_result = self.tts.setAudioAttributes(attrs)
                self.notify_app("TTS|AUDIO_ATTRIBUTES result=" + str(audio_result))
            except Exception as e:
                self.notify_app("TTS_ERROR|Audio attributes: " + str(e))

            self.notify_app("TTS|INIT_OK status=" + str(self.tts_init_status) + " language_result=" + str(result))
            if self.tts_language_ok:
                self.post(lambda: self.speak("VYRo voice system online."), 300)
            else:
                self.notify_app("TTS_ERROR|No supported English TTS language")
        except Exception as e:
            self.notify_app("TTS_ERROR|Language setup: " + str(e))

    def speak(self, text, queue=False):
        if not text:
            return False
        # Recognition callbacks can arrive on a Binder thread. Always route
        # actual TextToSpeech calls through Android's main looper.
        self.post(lambda txt=str(text), q=queue: self._speak_now(txt, q), 0)
        self.notify_app("TTS|SPEAK_QUEUED text=" + str(text)[:180])
        return True

    # ---------------- Recognition ----------------
    def make_intent(self):
        intent = self.Intent(self.RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
        intent.putExtra(
            self.RecognizerIntent.EXTRA_LANGUAGE_MODEL,
            self.RecognizerIntent.LANGUAGE_MODEL_FREE_FORM,
        )
        intent.putExtra(self.RecognizerIntent.EXTRA_PARTIAL_RESULTS, True)
        intent.putExtra(self.RecognizerIntent.EXTRA_MAX_RESULTS, 5)
        intent.putExtra(self.RecognizerIntent.EXTRA_LANGUAGE, "en-IN")

        # Give Android/Google a chance to switch between English and Hindi.
        try:
            allowed = self.ArrayList()
            allowed.add("en-IN")
            allowed.add("hi-IN")
            intent.putExtra(
                self.RecognizerIntent.EXTRA_ENABLE_LANGUAGE_DETECTION, True
            )
            intent.putExtra(
                self.RecognizerIntent.EXTRA_ENABLE_LANGUAGE_SWITCH,
                self.RecognizerIntent.LANGUAGE_SWITCH_BALANCED,
            )
            intent.putExtra(
                self.RecognizerIntent.EXTRA_LANGUAGE_DETECTION_ALLOWED_LANGUAGES,
                allowed,
            )
            intent.putExtra(
                self.RecognizerIntent.EXTRA_LANGUAGE_SWITCH_ALLOWED_LANGUAGES,
                allowed,
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
                self.notify_app("ERROR|Speech recognition service is not available")
                self.schedule_restart(5000)
                return

            if self.recognizer is not None:
                try:
                    self.recognizer.cancel()
                    self.recognizer.destroy()
                except Exception:
                    pass
                self.recognizer = None

            # createSpeechRecognizer/startListening are intentionally executed
            # on Android's main looper.
            self.recognizer = self.SpeechRecognizer.createSpeechRecognizer(self.context)
            self.recognizer.setRecognitionListener(self.listener)
            self.recognizer.startListening(self.make_intent())
            self.notify_app("STATUS|LISTENING — say VYRo")
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
            arr = results.getStringArrayList(self.SpeechRecognizer.RESULTS_RECOGNITION)
            if arr and arr.size() > 0:
                text = str(arr.get(0))
                self.notify_app("PARTIAL|" + text)
                # Wake detection must happen even before final results.
                self.process_text(text, True)
        except Exception as e:
            self.notify_app("ERROR|Partial result: " + str(e))

    def on_results(self, results):
        try:
            arr = results.getStringArrayList(self.SpeechRecognizer.RESULTS_RECOGNITION)
            if arr and arr.size() > 0:
                candidates = [str(arr.get(i)) for i in range(min(arr.size(), 5))]
                self.notify_app("RESULTS|" + " || ".join(candidates))
                # Try every candidate. This matters when Google's top result
                # is a near-spelling while another candidate contains VYRo.
                for text in candidates:
                    if self.contains_wake(text):
                        self.process_text(text, False)
                        return
                self.process_text(candidates[0], False)
            else:
                self.schedule_restart(700)
        except Exception as e:
            self.notify_app("ERROR|Final result: " + str(e))
            self.schedule_restart(1000)

    def on_error(self, error):
        if error == 7:  # ERROR_NO_MATCH
            self.notify_app("STATUS|LISTENING — say VYRo")
            self.schedule_restart(350)
            return

        names = {
            1: "network error", 2: "network timeout", 3: "audio error",
            4: "server error", 5: "client error", 6: "speech timeout",
            8: "recognizer busy", 9: "insufficient permissions",
            10: "language unavailable", 11: "language not supported",
            12: "server disconnected", 13: "cannot listen while in call",
        }
        self.notify_app(
            "ERROR|SpeechRecognizer " + str(error) + ": " + names.get(error, "unknown error")
        )
        self.schedule_restart(1200)

    # ---------------- Wake word ----------------
    @staticmethod
    def normalize_voice_text(text):
        text = str(text).lower().strip()
        replacements = {
            "jar vis": "jarvis",
            "jaar vis": "jarvis",
            "jaarvis": "jarvis",
            "jarvish": "jarvis",
            "jarvice": "jarvis",
            "jarvies": "jarvis",
            "jarvys": "jarvis",
            "jervis": "jarvis",
            "जार्विस": "jarvis",
            "जारविस": "jarvis",
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        text = re.sub(r"[^a-z0-9]+", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    @classmethod
    def contains_wake(cls, text):
        normalized = cls.normalize_voice_text(text)
        if "jarvis" in normalized:
            return True

        # Fuzzy fallback for speech-recognition spellings such as
        # "jarvies", "jervis", or other one-character ASR variations.
        for token in normalized.split():
            if len(token) < 4:
                continue
            ratio = difflib.SequenceMatcher(None, token, "jarvis").ratio()
            if ratio >= 0.70 and token[0] in {"j", "g"}:
                return True
        return False

    @classmethod
    def remove_wake(cls, text):
        cleaned = str(text)
        patterns = [
            r"(?i)jar\s*vis",
            r"(?i)jaar\s*vis",
            r"(?i)jarvish",
            r"(?i)jarvice",
            r"(?i)jarvies",
            r"(?i)jarvys",
            r"(?i)jervis",
            r"(?i)jarvis",
            r"जार्विस",
            r"जारविस",
        ]
        for pattern in patterns:
            cleaned = re.sub(pattern, "", cleaned)
        return re.sub(r"\s+", " ", cleaned).strip(" ,.!?")

    def activate_wake(self, original):
        # Debounce duplicate partial/final callbacks.
        now = time.time()
        if self.awake or (now - self.last_wake_at) < 1.2:
            return
        self.last_wake_at = now
        self.awake = True

        try:
            if self.recognizer is not None:
                self.recognizer.cancel()
                self.recognizer.destroy()
        except Exception:
            pass
        self.recognizer = None

        self.notify_app("WAKE|DETECTED: " + original)
        self.speak("Yes Boss. How can I help you?", queue=False)

        # Wait for acknowledgement speech to start before opening the next
        # recognition window.
        self.post(self.start_listening, 1800)

    def process_text(self, text, partial=False):
        text = re.sub(r"\s+", " ", str(text).strip())
        if not text:
            return
        self.last_text = text

        # Always expose what Android actually recognized in diagnostic builds.
        if partial:
            self.notify_app("RAW|PARTIAL: " + text)
        else:
            self.notify_app("RAW|FINAL: " + text)

        if self.contains_wake(text):
            remainder = self.remove_wake(text)
            self.notify_app("WAKECHECK|MATCH: " + text)
            if not self.awake:
                self.activate_wake(text)
                if remainder.strip():
                    self.post(lambda cmd=remainder.strip(): self.execute_command(cmd), 1700)
                return

        if partial:
            return

        self.notify_app("HEARD|" + text)

        if not self.awake:
            return

        self.awake = False
        low = self.normalize_voice_text(text)
        if low in {"cancel", "stop", "never mind", "nahi", "nahi chahiye", "rehne do"}:
            self.speak("Okay Boss.", queue=False)
            self.schedule_restart(700)
            return

        self.execute_command(text)

    def execute_command(self, command):
        try:
            from jarvis_core import JarvisCore
            data_file = os.path.join(self.files_dir, "jarvis_data.json")
            response = JarvisCore(data_file).handle(command)
            self.notify_app("COMMAND|" + command)
            self.speak(self.clean_for_speech(response), queue=True)
        except Exception as e:
            self.notify_app("ERROR|Command: " + str(e))
            self.speak("Sorry Boss, I could not process that command.", queue=True)
        finally:
            self.awake = False
            self.schedule_restart(1200)

    @staticmethod
    def clean_for_speech(text):
        text = str(text).replace("[DONE]", "done").replace("[ ]", "")
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
