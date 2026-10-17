import queue
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import tkinter as tk
import builtins
import getpass
import gui_worker

class GuiWorkerTests(unittest.TestCase):
    def test_output_converts_terminal_qr_without_ansi(self):
        events=queue.Queue()
        stream=gui_worker.WindowOutput(events)
        stream.write('\x1b[40m  \x1b[0m\x1b[47m  \x1b[0m')
        self.assertEqual(events.get(), ('output','██  '))

    def test_input_and_password_are_serviced_by_ui_thread(self):
        original_tk=tk.Tk
        result=[]
        calls=[]
        def make_root():
            root=original_tk()
            def finish():
                if len(result)==2:
                    root.after_cancel(timeout)
                    root.destroy()
                else:
                    root.after(20,finish)
            root.after(20,finish)
            timeout=root.after(3000,root.destroy)
            return root
        def fake_main():
            result.append(builtins.input('Code'))
            result.append(getpass.getpass('Password'))
        def ask(*args, **kwargs):
            import threading
            calls.append((threading.current_thread() is threading.main_thread(),kwargs['show']))
            return 'test value'
        with patch.object(gui_worker.tk,'Tk',side_effect=make_root), patch.object(gui_worker.simpledialog,'askstring',side_effect=ask), patch.dict('sys.modules',{'main':SimpleNamespace(main=fake_main)}):
            gui_worker.run_worker()
        self.assertEqual(result,['test value','test value'])
        self.assertEqual(calls,[(True,''),(True,'*')])

if __name__=='__main__':
    unittest.main()
