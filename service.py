import os
import re
import time
import difflib
from jnius import autoclass, PythonJavaClass, java_method

class CallbackRunnable(PythonJavaClass):
    __javainterfaces__ = ["java/lang/Runnable"]
    def __init__(self, cb): super().__init__(); self.cb = cb
    @java_method("()V")
    def run(self): self.cb()

class RecognitionListener(PythonJavaClass):
    __javainterfaces__ = ["android/speech/RecognitionListener"]
    def __init__(self, owner): super().__init__(); self.owner = owner
    @java_method("(Landroid/os/Bundle;)V")
    def onReadyForSpeech(self, p): self.owner.log("READY")
    @java_method("()V")
    def onBeginningOfSpeech(self): self.owner.log("HEARING")
    @java_method("([F)V")
    def onRmsChanged(self, v): pass
    @java_method("([B)V")
    def onBufferReceived(self, b): pass
    @java_method("()V")
    def onEndOfSpeech(self): pass
    @java_method("(I)V")
    def onError(self, e): self.owner.on_error(int(e))
    @java_method("(Landroid/os/Bundle;)V")
    def onResults(self, r): self.owner.on_results(r)
    @java_method("(Landroid/os/Bundle;)V")
    def onPartialResults(self, r): self.owner.on_partial(r)
    @java_method("(ILandroid/os/Bundle;)V")
    def onEvent(self, e, p): pass
    @java_method("(Landroid/os/Bundle;)V")
    def onLanguageDetection(self, r): pass

class TTSInit(PythonJavaClass):
    __javainterfaces__ = ["android/speech/tts/TextToSpeech$OnInitListener"]
    def __init__(self, owner): super().__init__(); self.owner = owner
    @java_method("(I)V")
    def onInit(self, status):
        self.owner.tts_ready = int(status) == self.owner.TTS.SUCCESS
        if self.owner.tts_ready: self.owner.post(self.configure_tts, 100)
        else: self.owner.log("TTS_INIT_FAILED|" + str(status))

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
        self.NotificationChannel = autoclass("android.app.NotificationChannel")
        self.NotificationManager = autoclass("android.app.NotificationManager")
        self.NotificationBuilder = autoclass("android.app.Notification$Builder")
        self.Build = autoclass("android.os.Build")
        self.context = self.PythonService.mService
        self.handler = self.Handler(self.Looper.getMainLooper())
        self.listener = RecognitionListener(self)
        self.tts_listener = TTSInit(self)
        self.recognizer = None
        self.tts = None
        self.tts_ready = False
        self.tts_language_ok = False
        self.active = True
        self.mode = "WAKE"
        self.waiting_command = False
        self.last_wake = 0.0
        self.restart_pending = False
        self.runnables = []
        self.files_dir = str(self.context.getFilesDir().getAbsolutePath())
        self.event_file = os.path.join(self.files_dir, "vyro_voice_events.txt")
        self.log("SERVICE_STARTED|VYRo V1.8.1")
        self.post(self.make_foreground, 100)
        self.post(self.init_tts, 250)
        self.post(self.start_listening, 1200)

    def log(self, event):
        try:
            with open(self.event_file, "a", encoding="utf-8") as f: f.write(str(event).replace("\n", " ") + "\n")
        except Exception: pass

    def post(self, fn, delay=0):
        holder = []
        def wrapped():
            try: fn()
            except Exception as e: self.log("ERROR|" + str(e))
            finally:
                if holder and holder[0] in self.runnables:
                    self.runnables.remove(holder[0])
        r = CallbackRunnable(wrapped); holder.append(r); self.runnables.append(r)
        if delay: self.handler.postDelayed(r, delay)
        else: self.handler.post(r)

    def make_foreground(self):
        try:
            channel_id = "vyro_voice"
            if self.Build.VERSION.SDK_INT >= 26:
                ch = self.NotificationChannel(channel_id, "VYRo Voice Assistant", self.NotificationManager.IMPORTANCE_LOW)
                nm = self.context.getSystemService("notification")
                nm.createNotificationChannel(ch)
                builder = self.NotificationBuilder(self.context, channel_id)
            else:
                builder = self.NotificationBuilder(self.context)
            builder.setContentTitle("VYRo is running")
            builder.setContentText("Voice assistant is active in background")
            builder.setSmallIcon(self.context.getApplicationInfo().icon)
            notification = builder.build()
            if self.Build.VERSION.SDK_INT >= 29:
                # FOREGROUND_SERVICE_TYPE_MICROPHONE = 128
                self.context.startForeground(1001, notification, 128)
            else:
                self.context.startForeground(1001, notification)
            self.log("FOREGROUND_OK")
        except Exception as e:
            self.log("FOREGROUND_ERROR|" + str(e))

    def init_tts(self):
        try:
            self.tts = self.TTS(self.context, self.tts_listener)
        except Exception as e: self.log("TTS_CREATE_ERROR|" + str(e))

    def configure_tts(self):
        try:
            result = self.tts.setLanguage(self.Locale("en", "IN"))
            if result in (self.TTS.LANG_MISSING_DATA, self.TTS.LANG_NOT_SUPPORTED): result = self.tts.setLanguage(self.Locale.US)
            self.tts_language_ok = result not in (self.TTS.LANG_MISSING_DATA, self.TTS.LANG_NOT_SUPPORTED)
            self.log("TTS_READY|" + str(result))
        except Exception as e: self.log("TTS_CONFIG_ERROR|" + str(e))

    def speak(self, text, after_ms=0):
        if not text: return
        def do():
            try:
                if self.tts and self.tts_ready and self.tts_language_ok:
                    # Stable 3-argument overload; no UtteranceProgressListener.
                    self.tts.speak(str(text), self.TTS.QUEUE_FLUSH, None)
            except Exception as e: self.log("TTS_SPEAK_ERROR|" + str(e))
        self.post(do, after_ms)

    def intent(self):
        i = self.Intent(self.RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
        i.putExtra(self.RecognizerIntent.EXTRA_LANGUAGE_MODEL, self.RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
        i.putExtra(self.RecognizerIntent.EXTRA_PARTIAL_RESULTS, True)
        i.putExtra(self.RecognizerIntent.EXTRA_MAX_RESULTS, 5)
        i.putExtra(self.RecognizerIntent.EXTRA_LANGUAGE, "en-IN")
        try:
            langs = self.ArrayList(); langs.add("en-IN"); langs.add("hi-IN")
            i.putExtra(self.RecognizerIntent.EXTRA_ENABLE_LANGUAGE_DETECTION, True)
            i.putExtra(self.RecognizerIntent.EXTRA_ENABLE_LANGUAGE_SWITCH, self.RecognizerIntent.LANGUAGE_SWITCH_BALANCED)
            i.putExtra(self.RecognizerIntent.EXTRA_LANGUAGE_DETECTION_ALLOWED_LANGUAGES, langs)
            i.putExtra(self.RecognizerIntent.EXTRA_LANGUAGE_SWITCH_ALLOWED_LANGUAGES, langs)
        except Exception: pass
        return i

    def start_listening(self):
        if not self.active or self.restart_pending: return
        self.restart_pending = False
        try:
            if self.recognizer:
                try: self.recognizer.cancel(); self.recognizer.destroy()
                except Exception: pass
            self.recognizer = self.SpeechRecognizer.createSpeechRecognizer(self.context)
            self.recognizer.setRecognitionListener(self.listener)
            self.recognizer.startListening(self.intent())
            self.log("LISTENING|" + self.mode)
        except Exception as e:
            self.log("RECOGNIZER_ERROR|" + str(e)); self.schedule(1500)

    def schedule(self, ms=700):
        if not self.active or self.restart_pending: return
        self.restart_pending = True
        self.post(self.start_listening, ms)

    def on_partial(self, results):
        try:
            a = results.getStringArrayList(self.SpeechRecognizer.RESULTS_RECOGNITION)
            if a and a.size(): self.process(str(a.get(0)), True)
        except Exception: pass

    def on_results(self, results):
        try:
            a = results.getStringArrayList(self.SpeechRecognizer.RESULTS_RECOGNITION)
            if not a or not a.size(): self.schedule(400); return
            candidates = [str(a.get(i)) for i in range(min(5, a.size()))]
            if self.mode == "WAKE":
                for x in candidates:
                    if self.contains_wake(x): self.process(x, False); return
                self.schedule(250); return
            self.process(candidates[0], False)
        except Exception as e:
            self.log("RESULT_ERROR|" + str(e)); self.schedule(600)

    def on_error(self, error):
        if error == 7: self.schedule(250)
        elif error in (6, 8): self.schedule(450)
        else: self.log("RECOGNIZER_ERROR_CODE|" + str(error)); self.schedule(1200)

    @staticmethod
    def norm(s):
        s = str(s).lower().strip()
        reps = {"vy ro":"vyro", "v y ro":"vyro", "vairo":"vyro", "viro":"vyro", "vyr":"vyro", "वायरो":"vyro", "वाय रो":"vyro"}
        for a,b in reps.items(): s=s.replace(a,b)
        s=re.sub(r"[^a-z0-9\u0900-\u097f]+", " ", s)
        return re.sub(r"\s+", " ", s).strip()

    @classmethod
    def contains_wake(cls, s):
        n=cls.norm(s)
        if "vyro" in n: return True
        for t in n.split():
            if len(t)>=3 and difflib.SequenceMatcher(None,t,"vyro").ratio()>=0.72: return True
        return False

    @classmethod
    def remove_wake(cls, s):
        s=str(s)
        for p in [r"(?i)v\s*y\s*r\s*o",r"(?i)vyro",r"(?i)vairo",r"(?i)viro",r"वायरो",r"वाय\s*रो"]: s=re.sub(p,"",s)
        return re.sub(r"\s+"," ",s).strip(" ,.!?")

    def process(self, text, partial):
        text=re.sub(r"\s+"," ",str(text).strip())
        if not text: return
        if self.mode == "WAKE":
            if not self.contains_wake(text): return
            now=time.time()
            if now-self.last_wake<1.2: return
            self.last_wake=now
            remainder=self.remove_wake(text)
            try:
                if self.recognizer: self.recognizer.cancel(); self.recognizer.destroy()
            except Exception: pass
            self.recognizer=None
            self.mode="COMMAND"; self.waiting_command=True
            self.speak("Yes Boss. How can I help you?")
            if remainder:
                self.post(lambda r=remainder: self.execute(r), 1600)
            else:
                self.schedule(1800)
            return
        if partial: return
        self.execute(text)

    def execute(self, command):
        from jarvis_core import JarvisCore
        try:
            data_file=os.path.join(self.files_dir,"jarvis_data.json")
            low=re.sub(r"[^a-z0-9]+"," ",str(command).lower()).strip()
            if low in {"exit","shutdown","shut down","close vyro","stop vyro","band ho jao","band ho"}:
                self.speak("Okay Boss. VYRo voice system is shutting down.")
                self.active=False; self.mode="STOPPED"
                try:
                    if self.recognizer: self.recognizer.cancel(); self.recognizer.destroy()
                except Exception: pass
                try: self.context.stopSelf()
                except Exception: pass
                return
            response=JarvisCore(data_file).handle(command)
            self.log("COMMAND|"+str(command)+"|"+str(response))
            self.speak(self.clean(response))
            # Critical: remain in conversation mode after every successful command.
            self.mode="COMMAND"; self.waiting_command=True
            self.speak("Any other help chahiye Sir aapko?", 1800)
            self.schedule(3300)
        except Exception as e:
            self.log("COMMAND_ERROR|"+str(e)); self.speak("Sorry Boss, I could not process that command."); self.mode="COMMAND"; self.schedule(1800)

    @staticmethod
    def clean(s):
        s=re.sub(r"\[[^\]]+\]", "", str(s)); s=re.sub(r"\s+"," ",s).strip(); return s[:700]

def main():
    VoiceService()
    while True: time.sleep(2)

if __name__ == "__main__": main()
