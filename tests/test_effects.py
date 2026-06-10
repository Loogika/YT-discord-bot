import unittest

from loogika.music.effects import AUDIO_EFFECTS, get_audio_effect


class AudioEffectTests(unittest.TestCase):
    def test_all_effects_keep_ffmpeg_pcm_output_options(self) -> None:
        for effect in AUDIO_EFFECTS.values():
            options = effect.ffmpeg_options("-vn")
            self.assertTrue(options.startswith("-vn"))

    def test_effect_opus_parameters_are_valid(self) -> None:
        valid_bandwidths = {"narrow", "medium", "wide", "superwide", "full"}
        valid_applications = {"audio", "voip", "lowdelay"}
        valid_signal_types = {"auto", "voice", "music"}

        for effect in AUDIO_EFFECTS.values():
            self.assertGreaterEqual(effect.opus_bitrate, 16)
            self.assertLessEqual(effect.opus_bitrate, 512)
            self.assertIn(effect.opus_bandwidth, valid_bandwidths)
            self.assertIn(effect.opus_application, valid_applications)
            self.assertIn(effect.opus_signal_type, valid_signal_types)

    def test_unknown_effect_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            get_audio_effect("missing")


if __name__ == "__main__":
    unittest.main()
