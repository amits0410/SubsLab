import tempfile
import unittest
from pathlib import Path

from subsgen.domain import SubtitleDocument, SubtitleLayoutSettings, SubtitleSegment, TimedWord, TranscriptionMode
from subsgen.recovery import RecoveryStore


class RecoveryTests(unittest.TestCase):
    def test_round_trip_and_clear(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RecoveryStore(Path(directory) / "recovery.json")
            source = SubtitleDocument(
                segments=[SubtitleSegment("a", 0, 1000, "שלום")],
                media_path=Path("movie.mp4"),
                srt_path=Path("movie.srt"),
                language="he",
                mode=TranscriptionMode.TRANSCRIBE,
                source_words=[TimedWord("שלום", 0, 500)],
                layout_settings=SubtitleLayoutSettings(max_cps=18),
                glossary=("OpenAI", "תל אביב"),
            )
            store.save(source, {"undo": [{"selected_id": "a"}]})
            restored = store.load()
            self.assertEqual(restored.segments[0].text, "שלום")
            self.assertEqual(restored.media_path, Path("movie.mp4"))
            self.assertEqual(restored.source_words[0].text, "שלום")
            self.assertEqual(restored.layout_settings.max_cps, 18)
            self.assertEqual(restored.glossary, ("OpenAI", "תל אביב"))
            self.assertEqual(store.load_editor_state()["undo"][0]["selected_id"], "a")
            store.clear()
            self.assertFalse(store.exists())


if __name__ == "__main__":
    unittest.main()
