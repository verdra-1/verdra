# Design laws

The owner's rules for every screen, dialog, menu and notice (16 and 19 October 2026, decision
record [0027](../decisions/0027-design-direction.md)). They bind the D1 audit, D2's mock-ups and
every D3 change, and they outrank a mock-up: a mock-up that breaks a law is changed, not the law.

## Law 1: nothing is cut off

Every button, label, tab, menu item, badge, tooltip title and dialog shows its full text:

- at text scale 100, 115, 150 and 200 % (the owner uses 115 %);
- at the minimum window size;
- in light, in dark, and in the four Windows contrast themes;
- in the pseudo-language: strings under 20 characters doubled, longer ones 40 % longer, with
  accents (so a German or French translation fits too).

Buttons grow and rows wrap; nothing elides. A CI check enforces it (D1): it opens every screen and
dialog at those scales and in the pseudo-language, walks every visible widget and fails when a
text's measured width (QFontMetrics) is wider than its room, or a label is elided.

## Law 2: only free-length data may shorten

Paths, links, asset names and log messages may shorten, and only:

- in the middle, keeping the file name whole ("C:\Users\…\verdra-test-1600x900.png");
- with the full text on hover, selectable and copyable.

The Activity message column wraps, or opens a detail pane with the full message.

## Further rules

- One filled primary button per view.
- Plain words first, details second.
- The same job has the same look everywhere.
- Color is never alone: always with a shape, an icon or a word (the status leaf has a shape per
  state, decision record 0027).
- Calm motion, and none when Windows or Settings asks for reduced motion.
- A 4 px grid for every size and space.
- Full keyboard and screen-reader support (plan 12.5).
- Windows contrast themes map to the system colors: Window, WindowText, Hotlight,
  Highlight/HighlightText and GrayText.
- The design pass covers backgrounds, surfaces, empty states, first run, error and offline
  states, and is planned from real user journeys: first start, add a replacement, apply, join,
  something goes wrong, come back a week later. Not screen by screen.
