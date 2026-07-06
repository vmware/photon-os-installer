# /*
#  * Copyright © 2026 VMware, Inc.
#  * SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
#  */
"""Generic pexpect-based driver for curses TUI programs.

This is used to script the interactive photon-os-installer dialogs (or any
other curses program) as a plain subprocess: send it key sequences, wait for
known marker text to confirm which screen is currently on display, and read
back whatever it prints once it exits.

Screens are identified by matching literal marker text (e.g. a window
title) rather than by rendering a full terminal screen buffer. A curses
redraw is still a byte stream that contains the literal strings the program
writes (window titles, prompts, error messages), so `expect_text()`
reliably tells us which screen is currently up before we act on it. The one
thing this approach can't do is tell which menu item currently has the
highlight (that's conveyed by color/reverse-video attributes, not text) -
callers work around that by scripting a fixed, known-good key sequence for
each screen instead of reading back the highlighted item.

TERM is fixed to "linux" rather than left to the environment: its terminfo
entry maps arrow keys to the plain `ESC [ A/B/C/D` sequences, whereas e.g.
"xterm"'s terminfo uses `ESC O A/B/C/D`. Using a fixed, known TERM keeps the
key byte sequences below correct regardless of what terminal the tests
happen to run under.
"""

import pexpect

TERM = "linux"

# Key byte sequences matching the "linux" terminfo entry's keypad mode.
_KEYS = {
    "enter": "\n",
    "tab": "\t",
    "up": "\x1b[A",
    "down": "\x1b[B",
    "right": "\x1b[C",
    "left": "\x1b[D",
    "backspace": "\x7f",
    "space": " ",
}

DEFAULT_TIMEOUT = 10
# rows, cols - comfortably fits every installer screen (the widest is 80 cols).
DEFAULT_DIMENSIONS = (40, 100)


class TuiDriver:
    """Drives a curses program spawned in a pty via pexpect."""

    def __init__(self, command, cwd=None, env=None,
                 dimensions=DEFAULT_DIMENSIONS, timeout=DEFAULT_TIMEOUT):
        spawn_env = dict(env or {})
        spawn_env["TERM"] = TERM
        self.child = pexpect.spawn(
            command, cwd=cwd, env=spawn_env, dimensions=dimensions, timeout=timeout,
        )

    def expect_text(self, pattern, timeout=None):
        """Block until `pattern` (a literal string or regex) appears in the output."""
        try:
            return self.child.expect(pattern, timeout=timeout)
        except pexpect.ExceptionPexpect as exc:
            raise AssertionError(
                f"never saw {pattern!r} in the installer output.\n"
                f"--- output seen so far ---\n{self.child.before}"
            ) from exc

    def send_key(self, name):
        """Send a symbolic key: enter, tab, up, down, left, right, backspace, space."""
        self.child.send(_KEYS[name])

    def send_text(self, text):
        """Type literal text into the currently focused input field."""
        self.child.send(text)

    def close_and_get_result(self, timeout=None):
        """Wait for the child to exit; return (exit_status, all remaining output)."""
        self.expect_text(pexpect.EOF, timeout=timeout)
        remaining = self.child.before
        self.child.close()
        return self.child.exitstatus, remaining

    def terminate(self):
        if self.child.isalive():
            self.child.terminate(force=True)
