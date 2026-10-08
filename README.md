# VYRo V1.8 Background Voice

This build keeps the working VYRo V1.8 VoiceEngine as the recognition/command base and moves it into an Android foreground microphone service.

## Flow
VYRo -> "Yes Boss. How can I help you?" -> command -> response -> "Any other help chahiye Sir aapko?" -> next command.

The service is intended to keep running when the Kivy UI is closed/minimized. It stops on voice commands such as `Shutdown`, `Shut down`, `Exit`, or `OK thanks`.

`open Google`, `open YouTube`, `open Settings`, and Google voice search remain in the V1.8 command path.

## Important
Android 14+ requires microphone foreground-service declarations. The spec declares `FOREGROUND_SERVICE_MICROPHONE` and the service as `foregroundServiceType=microphone`.

The service is started only while the app is visible after microphone/notification permissions are requested.
