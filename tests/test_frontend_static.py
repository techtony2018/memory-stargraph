from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class FrontendStaticTests(unittest.TestCase):
    def test_canvas_supports_mobile_safari_touch_drag_and_tap_hover(self):
        styles = (ROOT / "public" / "styles.css").read_text()
        script = (ROOT / "public" / "app.js").read_text()

        self.assertIn("touch-action: none", styles)
        self.assertIn("-webkit-touch-callout: none", styles)
        self.assertIn('canvas.addEventListener("pointerdown"', script)
        self.assertIn('canvas.addEventListener("touchstart"', script)
        self.assertIn("showMobileNodeHint", script)
        self.assertIn("showContextMenu(node.slug", script)


if __name__ == "__main__":
    unittest.main()
