"""
Audio filter presets, applied live through mpv (no extra software needed).

LECTURE_VOICE is the setting the user picked by ear on a Zoom-recorded lecture: it lifts the muffled
100-300 Hz body (high-pass + a dip at 200 Hz), brings out the consonants (+5 dB at 2.5 kHz, +3 dB at 4 kHz),
compresses the loud/quiet gap, and mixes in a very quiet pink noise so Zoom's noise suppression no longer leaves
audible holes between words. The limiter needs ``level=0`` (otherwise it boosts the output back to 0 dBFS
and clips) and a short attack.

It is a complex filter graph, so mpv ties the audio to track 1 (``[aid1]``) while it is on.
"""

LECTURE_VOICE = (
    "[aid1]highpass=f=90,"
    "equalizer=f=200:t=q:w=1:g=-4,equalizer=f=2500:t=q:w=1:g=5,equalizer=f=4000:t=q:w=1:g=3,"
    "acompressor=threshold=-34dB:ratio=4:attack=3:release=120:makeup=6:knee=4[a];"
    "anoisesrc=color=pink:amplitude=0.004:sample_rate=48000[n];"
    "[a][n]amix=inputs=2:duration=first:normalize=0,"
    "alimiter=limit=0.8:attack=1:release=100:level=0[ao]"
)
