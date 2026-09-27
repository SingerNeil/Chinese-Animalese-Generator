from __future__ import annotations

import tempfile
import unittest
import wave
import shutil
from pathlib import Path

from chinese_animalese import Pause, Syllable, render, tokenize


class TokenizeTests(unittest.TestCase):
    def test_maps_full_pinyin_final_to_available_abbreviation(self) -> None:
        events = tokenize("会")
        self.assertEqual(events, [Syllable("会", "h", "ui", 4)])

    def test_handles_syllabic_consonant(self) -> None:
        self.assertEqual(tokenize("嗯"), [Syllable("嗯", "", "n", 2)])

    def test_preserves_tones_and_punctuation(self) -> None:
        events = tokenize("你好？")
        self.assertEqual(events[0], Syllable("你", "n", "i", 3))
        self.assertEqual(events[1], Syllable("好", "h", "ao", 3))
        self.assertNotIn(Pause(300), events)

    def test_empty_text_has_no_events(self) -> None:
        self.assertEqual(tokenize("  \n"), [])


class RenderTests(unittest.TestCase):
    def _assert_valid_wav(self, path: Path) -> None:
        self.assertTrue(path.is_file())
        self.assertGreater(path.stat().st_size, 1000)
        with wave.open(str(path), "rb") as audio:
            self.assertEqual(audio.getnchannels(), 1)
            self.assertEqual(audio.getframerate(), 44100)
            self.assertGreater(audio.getnframes(), 1000)

    def test_renders_both_backends(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            self._assert_valid_wav(
                render("欢迎来到桌宠小屋。", temp / "equalo.wav", backend="equalo")
            )
            self._assert_valid_wav(
                render("欢迎来到桌宠小屋。", temp / "mandarin.wav", backend="mandarin")
            )

    def test_renders_iong_fallback_and_syllabic_consonant(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            self._assert_valid_wav(
                render("熊嗯", temp / "equalo.wav", backend="equalo")
            )
            self._assert_valid_wav(
                render("熊嗯", temp / "mandarin.wav", backend="mandarin")
            )

    def test_default_seed_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            first = render("你好", temp / "first.wav", backend="equalo")
            second = render("你好", temp / "second.wav", backend="equalo")
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_renders_all_dehiss_modes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            for mode in ("off", "filter", "remap"):
                self._assert_valid_wav(
                    render("学习休息", temp / f"{mode}.wav", dehiss=mode)
                )

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg is not installed")
    def test_speed_control_changes_duration(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            slow = render("欢迎来到桌宠小屋", temp / "slow.wav", speed=0.75)
            fast = render("欢迎来到桌宠小屋", temp / "fast.wav", speed=1.35)
            with wave.open(str(slow), "rb") as audio:
                slow_duration = audio.getnframes() / audio.getframerate()
            with wave.open(str(fast), "rb") as audio:
                fast_duration = audio.getnframes() / audio.getframerate()
            self.assertGreater(slow_duration, fast_duration)

    def test_rejects_unspeakable_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(ValueError):
                render("！？", Path(temp_dir) / "empty.wav")


if __name__ == "__main__":
    unittest.main()
