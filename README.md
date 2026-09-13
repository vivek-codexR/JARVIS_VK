# VYRo V1.7

V1.7 is built from the supplied V1.6.3 source.

## Main upgrades
- Preserves the working 3-argument Android TTS overload.
- Keeps SpeechRecognizer operations on Android's main looper.
- Adds better main-thread exception reporting.
- Adds duplicate-command cooldown.
- Adds a RESTART VOICE button.
- Keeps Hindi + English recognition settings.
- Adds basic identity/status/thanks commands.
- Removes the broken UtteranceProgressListener implementation from the optional service.

## Important
The app currently uses Android SpeechRecognizer while the app is active. Background/always-on wake-word support is intentionally not enabled in V1.7.
