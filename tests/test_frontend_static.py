from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class FrontendStaticTests(unittest.TestCase):
    def test_canvas_supports_mobile_safari_touch_drag_tap_hint_and_pinch_zoom(self):
        styles = (ROOT / "public" / "styles.css").read_text()
        script = (ROOT / "public" / "app.js").read_text()

        self.assertIn("touch-action: none", styles)
        self.assertIn("-webkit-touch-callout: none", styles)
        self.assertIn('canvas.addEventListener("pointerdown"', script)
        self.assertIn('canvas.addEventListener("touchstart"', script)
        self.assertIn("beginPinchZoom", script)
        self.assertIn("updatePinchZoom", script)
        self.assertIn("setZoom(pinchGesture.initialZoom", script)
        self.assertIn("showMobileNodeHint", script)
        self.assertIn("showContextMenu(node.slug", script)

    def test_mobile_tap_shows_tooltip_and_long_press_selects_without_menu(self):
        script = (ROOT / "public" / "app.js").read_text()
        pointer_up_start = script.index('window.addEventListener("pointerup"')
        pointer_up_end = script.index('window.addEventListener("pointercancel"', pointer_up_start)
        pointer_up_block = script[pointer_up_start:pointer_up_end]
        self.assertIn("showMobileNodeHint", pointer_up_block)
        self.assertIn("selectOnTap: !isTouchLike", pointer_up_block)

        long_press_start = script.index("longPressTimer = window.setTimeout")
        long_press_end = script.index("}, 580);", long_press_start)
        long_press_block = script[long_press_start:long_press_end]

        self.assertIn("selectMobileNode", long_press_block)
        self.assertIn("suppressContextMenuUntil", long_press_block)
        self.assertNotIn("showMobileNodeHint", long_press_block)
        self.assertNotIn("showContextMenu", long_press_block)

    def test_media_viewer_is_available_from_node_menu(self):
        markup = (ROOT / "public" / "index.html").read_text()
        script = (ROOT / "public" / "app.js").read_text()

        self.assertIn('data-action="media"', markup)
        self.assertIn('id="modalMedia"', markup)
        self.assertIn("/api/entity-media/", script)
        self.assertIn("renderMediaItems", script)

    def test_attach_file_uses_browser_file_picker(self):
        markup = (ROOT / "public" / "index.html").read_text()
        script = (ROOT / "public" / "app.js").read_text()

        self.assertIn('id="modalFileInput"', markup)
        self.assertIn('type="file"', markup)
        self.assertIn("new FormData()", script)
        self.assertIn('formData.append("file"', script)
        self.assertIn("apiPostForm", script)
        self.assertIn('modalPrimaryButton.textContent = "Uploading..."', script)
        self.assertIn("modalFileInput.disabled = true", script)
        self.assertIn("modalEditor.disabled = true", script)


if __name__ == "__main__":
    unittest.main()
