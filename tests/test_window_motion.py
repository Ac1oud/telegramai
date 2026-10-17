import tkinter as tk
import unittest

from ui_effects import animate_window_open, animate_window_close, spring_out


class WindowMotionTests(unittest.TestCase):
    def test_visible_animation_never_resizes_window_or_controls(self):
        root = tk.Tk()
        animate_window_open(root, duration_ms=120)
        root.geometry("360x240")
        root.minsize(320, 200)
        panel = tk.Frame(root)
        panel.pack(fill="both", expand=True)
        sizes = []
        positions = []

        def sample():
            if root.winfo_ismapped():
                sizes.append((root.winfo_width(), root.winfo_height(), panel.winfo_width(), panel.winfo_height()))
                positions.append(root.winfo_y())
            root.after(8, sample)

        root.after(20, sample)
        root.after(220, lambda: animate_window_close(root, duration_ms=120))
        root.mainloop()
        self.assertGreater(len(sizes), 5)
        self.assertEqual(set(sizes), {(360, 240, 360, 240)})
        self.assertGreater(len(set(positions)), 2)

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
            root.after_cancel(timeout)
            observed.append((root.winfo_width(), root.winfo_height(), root.minsize(), root.attributes("-alpha")))
            animate_window_close(root, duration_ms=30)
            animate_window_close(root, duration_ms=30)

        root.after(130, check_and_close)
        timeout = root.after(1500, root.destroy)
        root.mainloop()
        self.assertFalse(errors)
        self.assertEqual(observed, [(360, 240, (320, 200), 1.0)])


if __name__ == "__main__":
    unittest.main()
