#!/usr/bin/env python3
"""Chinese text to Animalese-style audio proof of concept.

This is deliberately a small, inspectable concatenative synthesizer. It does
not use a speech model and it is not intended to produce intelligible speech.
Subtitles remain the source of meaning; the audio supplies character and pace.
"""

from __future__ import annotations

import argparse
import hashlib
import math
import random
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from pydub import AudioSegment
from pydub.silence import detect_nonsilent
from pypinyin import Style, lazy_pinyin


ROOT = Path(__file__).resolve().parent
MANDARIN_ASSETS = ROOT / "assets" / "mandarin"
EQUALO_ASSETS = ROOT / "assets" / "equalo"

VOICE_OCTAVE_OFFSETS = {
    "lowest": -0.28,
    "low": -0.12,
    "med": 0.0,
    "high": 0.18,
}

EQUALO_KEYS = [
    *list("abcdefghijklmnopqrstuvwxyz"),
    "th",
    "sh",
    "space",
    "pause",
]
EQUALO_FILE_BY_KEY = {
    key: f"sound{index:02d}.wav"
    for index, key in enumerate(EQUALO_KEYS, start=1)
}

INITIAL_TO_EQUALO = {
    "": None,
    "b": "b",
    "p": "p",
    "m": "m",
    "f": "f",
    "d": "d",
    "t": "t",
    "n": "n",
    "l": "l",
    "g": "g",
    "k": "k",
    "h": "h",
    "j": "j",
    "q": "q",
    "x": "x",
    "zh": "j",
    "ch": "c",
    "sh": "sh",
    "r": "r",
    "z": "z",
    "c": "c",
    "s": "s",
    "y": "y",
    "w": "w",
}

SIBILANT_REMAP = {
    "s": "z",
    "x": "j",
    "sh": "r",
}

SIBILANT_FILES = {
    "sound19.wav",  # s
    "sound24.wav",  # x
    "sound27.wav",  # th
    "sound28.wav",  # sh
}

# The Equalo bank has character sounds rather than Mandarin finals. Mapping a
# final to its dominant vowel gives Chinese rhythm without pretending that the
# result is intelligible Mandarin.
FINAL_TO_EQUALO = {
    "a": "a",
    "o": "o",
    "e": "e",
    "i": "i",
    "u": "u",
    "v": "u",
    "ai": "a",
    "ei": "e",
    "ao": "o",
    "ou": "o",
    "an": "a",
    "en": "e",
    "ang": "a",
    "eng": "e",
    "ong": "o",
    "er": "r",
    "ia": "a",
    "ie": "e",
    "iao": "o",
    "iou": "o",
    "iu": "o",
    "ian": "a",
    "in": "i",
    "iang": "a",
    "ing": "i",
    "iong": "o",
    "ua": "a",
    "uo": "o",
    "uai": "a",
    "uei": "e",
    "ui": "e",
    "uan": "a",
    "uen": "e",
    "un": "e",
    "uang": "a",
    "ueng": "e",
    "van": "a",
    "ve": "e",
    "vn": "u",
    "n": "n",
    "m": "m",
}

MANDARIN_FINAL_ALIASES = {
    "uei": "ui",
    "uen": "un",
}

MANDARIN_FINAL_COMPONENTS = {
    "iong": ("i", "ong"),
}

PUNCTUATION_PAUSES_MS = {
    ",": 120,
    "，": 120,
    "、": 90,
    ":": 150,
    "：": 150,
    ";": 180,
    "；": 180,
    ".": 260,
    "。": 260,
    "!": 300,
    "！": 300,
    "?": 300,
    "？": 300,
    "\n": 320,
}


@dataclass(frozen=True)
class Syllable:
    character: str
    initial: str
    final: str
    tone: int


@dataclass(frozen=True)
class LatinLetter:
    value: str


@dataclass(frozen=True)
class Pause:
    duration_ms: int


Event = Syllable | LatinLetter | Pause


def _passthrough_errors(value: str) -> list[str]:
    return list(value)


def _is_cjk(character: str) -> bool:
    if not character:
        return False
    codepoint = ord(character)
    return (
        0x3400 <= codepoint <= 0x4DBF
        or 0x4E00 <= codepoint <= 0x9FFF
        or 0xF900 <= codepoint <= 0xFAFF
    )


def _split_tone(final_with_tone: str) -> tuple[str, int]:
    match = re.fullmatch(r"(.+?)([1-5])", final_with_tone)
    if not match:
        return final_with_tone, 5
    return match.group(1), int(match.group(2))


def tokenize(text: str) -> list[Event]:
    """Convert text into Chinese syllables, Latin letters, and pauses."""
    if not text or not text.strip():
        return []

    initials = lazy_pinyin(
        text,
        style=Style.INITIALS,
        strict=True,
        errors=_passthrough_errors,
    )
    finals = lazy_pinyin(
        text,
        style=Style.FINALS_TONE3,
        strict=True,
        neutral_tone_with_five=True,
        errors=_passthrough_errors,
    )
    full_syllables = lazy_pinyin(
        text,
        style=Style.TONE3,
        neutral_tone_with_five=True,
        errors=_passthrough_errors,
    )

    if (
        len(initials) != len(text)
        or len(finals) != len(text)
        or len(full_syllables) != len(text)
    ):
        raise ValueError("Pinyin conversion did not preserve character alignment")

    events: list[Event] = []
    for character, initial, final_with_tone, full_syllable in zip(
        text, initials, finals, full_syllables
    ):
        if _is_cjk(character):
            final, tone = _split_tone(final_with_tone)
            if not final:
                final, tone = _split_tone(full_syllable)
            final = MANDARIN_FINAL_ALIASES.get(final, final)
            events.append(Syllable(character, initial, final, tone))
            continue

        if character in PUNCTUATION_PAUSES_MS:
            duration = PUNCTUATION_PAUSES_MS[character]
            if events and isinstance(events[-1], Pause):
                events[-1] = Pause(max(events[-1].duration_ms, duration))
            else:
                events.append(Pause(duration))
            continue

        if character.isspace():
            if events and not isinstance(events[-1], Pause):
                events.append(Pause(45))
            continue

        lowered = character.lower()
        if "a" <= lowered <= "z":
            events.append(LatinLetter(lowered))

    while events and isinstance(events[0], Pause):
        events.pop(0)
    while events and isinstance(events[-1], Pause):
        events.pop()
    return events


def _stable_seed(text: str, backend: str, voice: str) -> int:
    digest = hashlib.sha256(f"{backend}\0{voice}\0{text}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _trim_silence(segment: AudioSegment, padding_ms: int = 4) -> AudioSegment:
    if not segment or segment.dBFS == -math.inf:
        return segment
    ranges = detect_nonsilent(
        segment,
        min_silence_len=12,
        silence_thresh=max(segment.dBFS - 22, -52),
        seek_step=2,
    )
    if not ranges:
        return segment
    start = max(0, ranges[0][0] - padding_ms)
    end = min(len(segment), ranges[-1][1] + padding_ms)
    return segment[start:end]


def _shift_by_octaves(segment: AudioSegment, octaves: float) -> AudioSegment:
    factor = 2.0 ** octaves
    new_rate = max(1000, int(segment.frame_rate * factor))
    shifted = segment._spawn(segment.raw_data, overrides={"frame_rate": new_rate})
    return shifted.set_frame_rate(44100)


def _prepare_fragment(
    path: Path,
    octaves: float,
    target_dbfs: float = -17.0,
    shorten: float = 1.0,
    low_pass_hz: int | None = None,
    fade_ms: int = 4,
) -> AudioSegment:
    if not path.is_file():
        raise FileNotFoundError(f"Missing audio asset: {path}")
    with path.open("rb") as source_file:
        fragment = AudioSegment.from_file(source_file, format="wav").set_channels(1)
    fragment = _trim_silence(fragment)
    fragment = _shift_by_octaves(fragment, octaves)
    if low_pass_hz is not None:
        fragment = fragment.low_pass_filter(low_pass_hz)
    if shorten < 1.0 and len(fragment) > 1:
        fragment = fragment[: max(1, int(len(fragment) * shorten))]
    if fragment.dBFS != -math.inf:
        gain = max(-12.0, min(12.0, target_dbfs - fragment.dBFS))
        fragment = fragment.apply_gain(gain)
    fade = min(fade_ms, max(0, len(fragment) // 3))
    if fade:
        fragment = fragment.fade_in(fade).fade_out(fade)
    return fragment


def _tone_offset(tone: int, component_index: int, component_count: int) -> float:
    progress = component_index / max(1, component_count - 1)
    if tone == 1:
        return 0.10
    if tone == 2:
        return -0.10 + 0.28 * progress
    if tone == 3:
        return -0.12 + 0.12 * progress
    if tone == 4:
        return 0.18 - 0.38 * progress
    return -0.10


def _mandarin_paths(syllable: Syllable) -> list[Path]:
    paths: list[Path] = []
    if syllable.initial:
        paths.append(MANDARIN_ASSETS / f"{syllable.initial}.wav")
    if syllable.final:
        final_components = MANDARIN_FINAL_COMPONENTS.get(
            syllable.final, (syllable.final,)
        )
        paths.extend(MANDARIN_ASSETS / f"{component}.wav" for component in final_components)
    return paths


def _equalo_path(voice: str, key: str) -> Path:
    filename = EQUALO_FILE_BY_KEY[key]
    return EQUALO_ASSETS / voice / filename


def _equalo_paths(syllable: Syllable, voice: str, dehiss: str) -> list[Path]:
    keys: list[str] = []
    initial_key = INITIAL_TO_EQUALO.get(syllable.initial)
    if dehiss == "remap" and initial_key:
        initial_key = SIBILANT_REMAP.get(initial_key, initial_key)
    if initial_key:
        keys.append(initial_key)
    if not syllable.final and keys:
        return [_equalo_path(voice, key) for key in keys]
    final_key = FINAL_TO_EQUALO.get(syllable.final)
    if not final_key:
        raise KeyError(
            f"No Equalo mapping for final '{syllable.final}' "
            f"from character '{syllable.character}'"
        )
    keys.append(final_key)
    return [_equalo_path(voice, key) for key in keys]


def _append_fragment(output: AudioSegment, fragment: AudioSegment) -> AudioSegment:
    if not output:
        return fragment
    crossfade = min(5, len(output), len(fragment))
    return output.append(fragment, crossfade=crossfade)


def _apply_tempo(output_path: Path, speed: float) -> None:
    if math.isclose(speed, 1.0, rel_tol=0.0, abs_tol=0.001):
        return
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError(
            "FFmpeg is required when speed is not 1.0. Install FFmpeg and restart the app."
        )

    with tempfile.NamedTemporaryFile(
        prefix="animalese-tempo-",
        suffix=".wav",
        dir=output_path.parent,
        delete=False,
    ) as temp_file:
        temp_path = Path(temp_file.name)

    try:
        process = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(output_path),
                "-filter:a",
                f"atempo={speed:.6f}",
                "-ar",
                "44100",
                "-ac",
                "1",
                str(temp_path),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if process.returncode != 0:
            detail = process.stderr.strip() or "unknown FFmpeg error"
            raise RuntimeError(f"Could not change speech speed: {detail}")
        temp_path.replace(output_path)
    finally:
        temp_path.unlink(missing_ok=True)


def render(
    text: str,
    output_path: Path,
    *,
    backend: str = "equalo",
    voice: str = "med",
    dehiss: str = "remap",
    speed: float = 1.0,
    pitch_semitones: float = 0.0,
    variation: float = 1.0,
    pause_scale: float = 1.0,
    seed: int | None = None,
) -> Path:
    if backend not in {"equalo", "mandarin"}:
        raise ValueError("backend must be 'equalo' or 'mandarin'")
    if voice not in VOICE_OCTAVE_OFFSETS:
        raise ValueError(f"unknown voice: {voice}")
    if dehiss not in {"off", "filter", "remap"}:
        raise ValueError("dehiss must be 'off', 'filter', or 'remap'")
    if not 0.5 <= speed <= 2.0:
        raise ValueError("speed must be between 0.5 and 2.0")
    if not -8.0 <= pitch_semitones <= 12.0:
        raise ValueError("pitch_semitones must be between -8 and 12")
    if not 0.0 <= variation <= 2.0:
        raise ValueError("variation must be between 0 and 2")
    if not 0.25 <= pause_scale <= 2.5:
        raise ValueError("pause_scale must be between 0.25 and 2.5")

    events = tokenize(text)
    if not events:
        raise ValueError("text did not contain any speakable characters")

    rng = random.Random(seed if seed is not None else _stable_seed(text, backend, voice))
    output = AudioSegment.silent(duration=0, frame_rate=44100).set_channels(1)

    syllable_positions = [i for i, event in enumerate(events) if isinstance(event, Syllable)]
    last_syllable_positions = set(syllable_positions[-3:]) if text.rstrip().endswith(("?", "？")) else set()

    for event_index, event in enumerate(events):
        if isinstance(event, Pause):
            output += AudioSegment.silent(
                duration=max(1, round(event.duration_ms * pause_scale)),
                frame_rate=44100,
            )
            continue

        if isinstance(event, LatinLetter):
            if backend != "equalo":
                continue
            path = _equalo_path(voice, event.value)
            octaves = 2.28 + VOICE_OCTAVE_OFFSETS[voice]
            octaves += pitch_semitones / 12.0
            octaves += rng.uniform(-0.13, 0.13) * variation
            low_pass_hz = 6200 if dehiss == "filter" and path.name in SIBILANT_FILES else None
            output = _append_fragment(
                output,
                _prepare_fragment(
                    path,
                    octaves,
                    low_pass_hz=low_pass_hz,
                    fade_ms=9 if low_pass_hz else 4,
                ),
            )
            continue

        paths = (
            _equalo_paths(event, voice, dehiss)
            if backend == "equalo"
            else _mandarin_paths(event)
        )
        if not paths:
            continue
        base_octaves = 2.28 if backend == "equalo" else 2.42
        base_octaves += VOICE_OCTAVE_OFFSETS[voice]
        base_octaves += pitch_semitones / 12.0
        for component_index, path in enumerate(paths):
            octaves = base_octaves
            octaves += rng.uniform(-0.13, 0.13) * variation
            octaves += _tone_offset(event.tone, component_index, len(paths))
            if event_index in last_syllable_positions:
                rank = sorted(last_syllable_positions).index(event_index)
                octaves += 0.06 + rank * 0.08
            shorten = 0.78 if event.tone == 5 else 1.0
            low_pass_hz = (
                6200
                if backend == "equalo"
                and dehiss == "filter"
                and path.name in SIBILANT_FILES
                else None
            )
            fragment = _prepare_fragment(
                path,
                octaves,
                shorten=shorten,
                low_pass_hz=low_pass_hz,
                fade_ms=9 if low_pass_hz else 4,
            )
            output = _append_fragment(output, fragment)

    if len(output) == 0:
        raise ValueError("no audio was generated")
    if output.max_dBFS > -1.0:
        output = output.apply_gain(-1.0 - output.max_dBFS)

    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as destination_file:
        output.export(destination_file, format="wav")
    _apply_tempo(output_path, speed)
    return output_path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate Chinese Animalese-style WAV audio."
    )
    parser.add_argument("text", help="Chinese text to synthesize")
    parser.add_argument(
        "--backend",
        choices=("equalo", "mandarin"),
        default="equalo",
        help="equalo uses the four character banks; mandarin uses Chinese phoneme clips",
    )
    parser.add_argument(
        "--voice",
        choices=tuple(VOICE_OCTAVE_OFFSETS),
        default="med",
        help="voice register",
    )
    parser.add_argument(
        "--dehiss",
        choices=("off", "filter", "remap"),
        default="remap",
        help="reduce harsh s/x/sh fragments by filtering or remapping them",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="tempo multiplier from 0.5 to 2.0 without changing pitch",
    )
    parser.add_argument(
        "--pitch",
        type=float,
        default=0.0,
        help="additional pitch shift in semitones from -8 to 12",
    )
    parser.add_argument(
        "--variation",
        type=float,
        default=1.0,
        help="random pitch variation from 0 to 2",
    )
    parser.add_argument(
        "--pause-scale",
        type=float,
        default=1.0,
        help="punctuation pause multiplier from 0.25 to 2.5",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "output" / "animalese.wav",
        help="output WAV path",
    )
    parser.add_argument("--seed", type=int, help="optional random seed")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    result = render(
        args.text,
        args.out,
        backend=args.backend,
        voice=args.voice,
        dehiss=args.dehiss,
        speed=args.speed,
        pitch_semitones=args.pitch,
        variation=args.variation,
        pause_scale=args.pause_scale,
        seed=args.seed,
    )
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
