from dataclasses import dataclass


@dataclass(frozen=True)
class AudioEffect:
    name: str
    description: str
    ffmpeg_filter: str | None
    opus_bitrate: int
    opus_bandwidth: str
    opus_application: str
    opus_signal_type: str

    def ffmpeg_options(self, base_options: str) -> str:
        if self.ffmpeg_filter is None:
            return base_options
        return f'{base_options} -af "{self.ffmpeg_filter}"'


AUDIO_EFFECTS = {
    "normal": AudioEffect(
        name="normal",
        description="Original sound",
        ffmpeg_filter=None,
        opus_bitrate=128,
        opus_bandwidth="full",
        opus_application="audio",
        opus_signal_type="auto",
    ),
    "phone": AudioEffect(
        name="phone",
        description="Narrow telephone call",
        ffmpeg_filter=(
            "highpass=f=300,"
            "lowpass=f=3400,"
            "acompressor=threshold=0.1:ratio=6:attack=5:release=50:makeup=2"
        ),
        opus_bitrate=24,
        opus_bandwidth="narrow",
        opus_application="voip",
        opus_signal_type="voice",
    ),
    "crushed": AudioEffect(
        name="crushed",
        description="Heavily compressed and bit-crushed audio",
        ffmpeg_filter=(
            "aresample=8000,"
            "acrusher=bits=6:samples=8:mix=0.8,"
            "lowpass=f=5000,"
            "aresample=48000"
        ),
        opus_bitrate=24,
        opus_bandwidth="medium",
        opus_application="lowdelay",
        opus_signal_type="music",
    ),
    "radio": AudioEffect(
        name="radio",
        description="Old compact radio",
        ffmpeg_filter=(
            "highpass=f=180,"
            "lowpass=f=4500,"
            "acompressor=threshold=0.08:ratio=8:attack=5:release=80:makeup=2,"
            "acrusher=bits=10:samples=2:mix=0.25"
        ),
        opus_bitrate=48,
        opus_bandwidth="wide",
        opus_application="audio",
        opus_signal_type="music",
    ),
}

DEFAULT_AUDIO_EFFECT = AUDIO_EFFECTS["normal"]


def get_audio_effect(name: str) -> AudioEffect:
    try:
        return AUDIO_EFFECTS[name]
    except KeyError as exc:
        raise ValueError(f"Unknown audio effect: {name}") from exc
