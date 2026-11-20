#ifndef SCRAP_HOST_AUDIO_CAPTURE_H
#define SCRAP_HOST_AUDIO_CAPTURE_H
/* Install optional read-only observations before the audio worker starts. */
void scrap_host_audio_observe_install(void);
/* Call after the producer has stopped; streaming headers are checkpointed
 * every second as well, so an interrupted diagnostic retains usable PCM. */
void scrap_host_audio_observe_finish(void);
#endif
