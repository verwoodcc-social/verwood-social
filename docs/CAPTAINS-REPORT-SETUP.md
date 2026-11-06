# Captain's match reports: Microsoft Form + Power Automate

Captains fill in a short Microsoft Form after a game. A Power Automate flow checks the club code and
sends the answers to GitHub, and the kit adds the captain's words to that game's result post:

> 🗣️ Captain's report – Sam Cole:
> “A great all-round performance…”
> ⭐ Player of the match: Ben T

The result post waits until **9:15am** the morning after for a report, then goes out anyway. If a report
arrives earlier, the result goes out within a few minutes.

**Choose a club code** first: a short word or number for captains only (e.g. `Potterne27`). It's checked
inside Power Automate, so it never appears on GitHub. Change it whenever you like.

## 1 · The form

Verwood's form (*Verwood CC – Captain's match report*) is already made. Its layout:

| Page | Question | Notes |
|---|---|---|
| 1 | Which section is the team in? | Adult Hardball, Women & Girls, Youth, Indoor. Branches to the matching page |
| 2 | Team (Adult Hardball) | Drop-down: 1st–5th XI, Wednesday 1st XI, Friendly XI |
| 3 | Team (Women & Girls) | Drop-down: Women's Softball, Women's Softball B, Girls U13, Girls U11 A/B |
| 4 | Team (Youth) | Drop-down: Under 19 down to Under 8 |
| 5 | Team (Indoor) | Drop-down: Indoor A–E, indoor softball and youth indoor sides |
| 6 | Match date, Captain, Report, Player of the match, Club code | Every branch ends here |

Team names must match Play-Cricket exactly. To add a team, add it to the right drop-down.

**Share the pre-filled link** so captains never type the code: ⋯ → *Get pre-filled URL*, click *Next*
through to the last page, type the club code, click *Get Prefilled Link* and *Copy link*. Anyone with
that link can submit, so keep it to captains. If it gets passed around, change the code in the form
and the flow, and make a new link.

## 2 · Make the flow (15 minutes)

At [make.powerautomate.com](https://make.powerautomate.com), signed in with the same account:

1. **Create → Automated cloud flow**. Name it *Captain's report to GitHub*. Choose the trigger
   **When a new response is submitted** (Microsoft Forms) and click **Create**. Pick your form.
2. **+ New step → Microsoft Forms → Get response details**. Form: your form. Response Id: pick
   **Response Id** from the dynamic content.
3. **+ New step → Condition**. Left box: **Club code** (dynamic content). Middle: *is equal to*. Right
   box: your club code.
4. In **If yes**, **Add an action → GitHub → Create an issue**. Sign in to GitHub as the club's
   GitHub account (verwoodcc-social) when asked, and allow access. Then fill in:
   - **Repository owner:** `verwoodcc-social`
   - **Repository name:** `verwood-social`
   - **Title:** type `Captain's report: ` then pick **Match date**
   - The team is in one of four questions (one per section). In the body, put all four next to each
     other under `### Team` (only the one the captain answered has anything in it).
   - **Body:** type exactly the lines below, replacing each *[ … ]* with that answer from the dynamic
     content (leave the blank lines in):

```
### Team

[Team (Adult Hardball)][Team (Women & Girls)][Team (Youth)][Team (Indoor)]

### Match date

[Match date]

### Captain

[Captain]

### Report

[Report]

### Player of the match

[Player of the match]
```

   - If there's a **Labels** box, put `captain-report` in it (optional).
5. Leave **If no** empty (wrong code: nothing happens). Click **Save**, then **Test → Manually**, and
   send a test response from the form. A new issue *Captain's report: …* should appear in the
   verwood-social Issues tab within a minute.

Don't put the club code in the issue body: the GitHub repository is public.

## Good to know

- Only issues opened through the club's GitHub connection count. Anyone else opening an issue with
  the same title is ignored.
- Links are removed from reports, and long reports are trimmed to about 700 characters.
- A report that doesn't match a result (wrong team or date), or arrives after the result was posted,
  is closed after 3 days with a note. Results for every team (senior and youth) wait for a report until 9:15am.
- Change the waiting time with `captain_reports → wait_until` in `club.yml`, or switch waiting off with
  `wait: false`.
