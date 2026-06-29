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

    def test_long_press_shows_tooltip_without_opening_mobile_menu(self):
        script = (ROOT / "public" / "app.js").read_text()
        long_press_start = script.index("longPressTimer = window.setTimeout")
        long_press_end = script.index("}, 580);", long_press_start)
        long_press_block = script[long_press_start:long_press_end]

        self.assertIn("showMobileNodeHint", long_press_block)
        self.assertNotIn("showContextMenu", long_press_block)

    def test_media_viewer_is_available_from_node_menu(self):
        markup = (ROOT / "public" / "index.html").read_text()
        script = (ROOT / "public" / "app.js").read_text()

        self.assertIn('data-action="media"', markup)
        self.assertIn('id="modalMedia"', markup)
        self.assertIn("/api/entity-media/", script)
        self.assertIn("renderMediaItems", script)


if __name__ == "__main__":
    unittest.main()
