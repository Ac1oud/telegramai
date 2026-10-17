import tkinter as tk
import unittest

from ui_effects import animate_window_open, animate_window_close, spring_out


class WindowMotionTests(unittest.TestCase):
    def test_spring_settles_after_a_small_overshoot(self):
        self.assertAlmostEqual(spring_out(0), 0)
        self.assertAlmostEqual(spring_out(1), 1)
        peak = max(spring_out(i / 100) for i in range(101))
        self.assertGreater(peak, 1)
        self.assertLess(peak, 1.1)

    def test_open_preserves_size_opacity_and_close_finishes_once(self):
        root = tk.Tk()
        errors = []
        root.report_callback_exception = lambda *error: errors.append(error)
        animate_window_open(root, duration_ms=30)
        root.geometry("360x240")
        root.minsize(320, 200)
        observed = []

        def check_and_close():
            observed.append((root.winfo_width(), root.winfo_height(), root.minsize(), root.attributes("-alpha")))
            animate_window_close(root, duration_ms=30)
            animate_window_close(root, duration_ms=30)

        root.after(130, check_and_close)
        root.after(1500, root.destroy)
        root.mainloop()
        self.assertFalse(errors)
        self.assertEqual(observed, [(360, 240, (320, 200), 1.0)])


if __name__ == "__main__":
    unittest.main()
