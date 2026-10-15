# The README animation. Regenerate it with:
#
#     python3 tools/demo/setup_demo.py     # builds the throwaway env under /tmp/tp-demo
#     vhs tools/demo/demo.tape             # writes docs/assets/demo.gif
#
# The two adapters are scripts, not models: the animation is about the mechanism
# (a claim, an independent verdict, a record) rather than about any one agent.
# Nothing here touches a real ledger — TASKPROOF_HOME points at the throwaway one.

Output docs/assets/demo.gif

Set Shell "bash"
Set FontFamily "Menlo, monospace"
Set FontSize 15
Set Width 1500
Set Height 380
Set Padding 20
Set Theme "Dracula"
Set TypingSpeed 12ms
Set CursorBlink false
Set Framerate 24

# The setup and the first command are typed while hidden, so the very first
# frame of the GIF already shows something instead of an empty prompt.
Hide
Type "cd /tmp/tp-demo/repo && export TASKPROOF_HOME=/tmp/tp-demo/state"
Enter
Sleep 500ms
Type "taskproof run demo-app 'fix the greeting in app.txt' --adapter custom:./agent-lies"
Show
Sleep 350ms
Enter
Sleep 7s

Type "# what the record says it did"
Enter
Sleep 600ms
Type "L=$(basename /tmp/tp-demo/state/logs/t-*-001.log .log)"
Enter
Sleep 400ms
Type "taskproof log $L | tail -5"
Enter
Sleep 3s

Type "# card 2: an agent that actually does the work"
Enter
Sleep 700ms
Type "taskproof run demo-app 'fix the greeting in app.txt' --adapter custom:./agent-fixes"
Enter
Sleep 7s
Type "taskproof tasks"
Enter
Sleep 4s
