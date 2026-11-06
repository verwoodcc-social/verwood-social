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

## 1 · Make the form (10 minutes)

At [forms.office.com](https://forms.office.com), signed in with your club account, click **New Form**.
Title: *Verwood CC – Captain's match report*. Add these questions, in this order:

| # | Question (exact wording) | Type | Required |
|---|---|---|---|
| 1 | Team | Choice, shown as a **drop-down**: every senior and youth team, named exactly as on Play-Cricket | Yes |
| 2 | Match date | Date | Yes |
| 3 | Captain | Text | Yes |
| 4 | Report | Text, **Long answer** | Yes |
| 5 | Player of the match | Text | No |
| 6 | Club code | Text | Yes |

Under question 4, add the subtitle: *3–6 sentences about the game. For anyone under 18, please use their
first name only.*

**Settings** (⋯ → Settings): *Anyone can respond*.

**Share the pre-filled link** so captains never type the code: ⋯ → *Get pre-filled URL*, switch on
*Enable pre-filled answers*, type the club code in question 6, click *Get Prefilled Link* and *Copy link*.
Send that link (not the plain one) to captains. Anyone with it can submit, so keep it to captains.

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
   - **Title:** type `Captain's report: ` then pick **Team**, type a space, pick **Match date**
   - **Body:** type exactly the lines below, replacing each *[ … ]* with that answer from the dynamic
     content (leave the blank lines in):

```
### Team

[Team]

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
