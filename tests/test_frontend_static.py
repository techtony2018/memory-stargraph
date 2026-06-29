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

    def test_long_press_menu_does_not_overlap_mobile_hover_tooltip(self):
        script = (ROOT / "public" / "app.js").read_text()
        long_press_start = script.index("longPressTimer = window.setTimeout")
        long_press_end = script.index("}, 580);", long_press_start)
        long_press_block = script[long_press_start:long_press_end]

        self.assertIn("hideGraphTooltip()", long_press_block)
        self.assertIn("showContextMenu(node.slug", long_press_block)
        self.assertNotIn("showMobileNodeHint", long_press_block)


if __name__ == "__main__":
    unittest.main()
