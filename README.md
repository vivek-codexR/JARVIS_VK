# VYRo V1.8.1

## Main changes
- VYRo wake-word detection with common ASR spellings.
- Wake -> "Yes Boss. How can I help you?" -> command.
- Command response -> "Any other help chahiye Sir aapko?" -> next command.
- Time/date/rules/timetable/tasks/summary and task/rule management.
- Exit/shutdown stops the voice service.
- UI close does not call service shutdown.
- Android foreground microphone service for background operation.
- Stable 3-argument TextToSpeech call; no UtteranceProgressListener.

## Build
GitHub Actions workflow builds a debug APK and verifies the APK with `unzip -t` before upload.
