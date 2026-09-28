# Mockups for the 2026-09-28 section-and-card standard

Throwaway, not product code. Each `.html` links the app's real `app.css`, then `mock.css`,
which is what the real change would add to the stylesheet and which existing rules it would
retire. `shoot.py` renders every page at 1440×900 and at 390×844 (2×, touch) with Playwright.

| File | What it shows |
|---|---|
| `cards.html` | The five-slot card drawn once for every container: a question, the same item opened, two Must-finish rows, a family step, a step the school has, a waiting card, the line density. Slots labelled on the first card |
| `assignments.html` | Doug's Assignments tab with the data from the 2026-09-28 screenshot: the state line, the sections, filters in the table's head, a row opened to the flat detail |
| `plan.html` | Doug's Plan tab: Must finish, Our next steps, Worth checking and Waiting as the one section and the one card, the green palette retired |

The sample data is Doug's on Mon 9/28 where the screenshot had it, and invented elsewhere.
