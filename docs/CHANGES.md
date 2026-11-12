# What's new

## 1.21.0 (12 November 2026)

- Word copies of the kit's documents: Markdown saved in SharePoint → Social media kit documents → Markdown is turned into Word documents in Social media kit documents (Actions → Word documents, daily at 05:11 UTC and on demand). Set in club.yml → word_docs.

## 1.20.0 (Verwood)

- Photos emailed to Media@verwoodcc.co.uk: the committee gets a morning email listing new photos waiting
  in To check (each photo is mentioned once).
- iPhone HEIC photos are converted to JPEG when the photo store is copied in.
- The monthly report email (not the sponsor PDF) ends with photo counts per team and the teams with none.

## 1.19.0 (Verwood)

- Photo store moved to the club SharePoint (Club Documents → Documents → Social media photos), so photos can
  be added from a phone or computer without a GitHub account (club.yml → photo_store).
- A folder for every current team, named exactly as on Play-Cricket. Check setup makes a folder for any
  team added to the list. Team names match whether Play-Cricket writes "Under 12" or "U12".

## 1.18.0 (Verwood)

- Weekly backup: every Sunday the kit and the private photo store are saved to the club SharePoint
  (club.yml → backup; setup in docs/BACKUP-SETUP.md). The newest 8 weeks are kept.
- Make posts: a "date" box to catch up a missed day.
- Instagram Stories are retried when Instagram says the image isn't ready yet.

## 1.17.0 (Verwood)

- Expiry reminders: every morning the kit checks when the Meta token, the player photos key and the
  Microsoft 365 email secret run out, and emails the committee 30 and 7 days before (club.yml →
  expiry_reminders). The reminder closes itself with a "renewed" email once the new key is saved.
  Check setup shows each expiry date.

## 1.16.0 (Verwood)
- **Captain's match reports:** a Microsoft Form + Power Automate flow (docs/CAPTAINS-REPORT-SETUP.md)
  sends a captain's few lines and player of the match to the kit, which adds them to that game's result
  post. Adult results wait until 9:15am for a report (a third morning run at about 9:20 makes sure they
  go out); a report arriving earlier posts its result within minutes. Settings under `captain_reports:`.

## 1.15.0 (Verwood)
- **Season fixture lists:** 1–7 April, one post per team (senior and youth) with all its outdoor summer
  fixtures (date, opponent, time, home/away), spread across the week so a few go out each morning:
  seniors first, then the juniors from oldest down. Settings under `season_fixtures:`.

## 1.14.0 (Verwood)
- **Season review:** first Monday of October, one carousel for the outdoor season: every adult team's
  record and league position, a slide per team (record, league finish, top 3 run scorers, wicket
  takers and catchers), the career milestones reached that season, and the all-time career leaders.
  Replaces October's monthly leaderboards. Settings under `season_review:`.

## 1.13.0 (Verwood)
- **League tables:** on the last day of each month, April to September, one carousel with the league
  table for each adult team (from Play-Cricket), Verwood's row highlighted, and a caption listing each
  team's position. Cups, junior and indoor leagues are left out; a team only appears once it has played.
  Settings under `league_tables:`. The setup check previews last season's final tables.

## 1.12.0 (Verwood)
- **Milestone watch:** with Friday's fixtures, a post (and Story) listing players close to a career
  milestone whose team plays that week, e.g. "Charlie Gajic needs 20 runs for 10,000 career runs".
  Players count if they've played for that team in the last 3 weeks. Settings under
  `career_milestones → watch`.
- Career milestones always use full names; a junior's photo is never shown with their name.
- `careers/links.csv` can add two CricketStatz records together for one player (`#1+#2`).

## 1.11.0 (Verwood)
- **Career milestones:** a post when a player reaches 500 career runs (then every 500), or 50 wickets,
  appearances, catches or catches as wicketkeeper (then every 50). Saturday, midweek and Sunday sides
  start from the CricketStatz totals to the end of 2026 (`careers/baseline.csv`) and add each outdoor
  Play-Cricket game from 2027. Women's Softball uses Play-Cricket only (all past outdoor seasons are
  added up once). Players are matched by Play-Cricket id (`careers/links.csv`); a few shared names need
  checking by hand. Indoor, junior and winter games aren't counted.
- Saved totals and the leaderboards cache now hold shortened names only.

## 1.10.0 (Verwood)
- **Problem alerts by email:** if the daily posts, a post, a club news preview or the sponsor report
  fails, a *problem* issue opens and the committee is emailed (through Microsoft 365, to ALERT_EMAIL_TO
  or REPORT_EMAIL_TO). Repeats don't send more emails. When it works again the issue closes itself and a
  short "fixed" email goes out. The daily posts only email if both morning runs fail, so a brief
  Play-Cricket blip doesn't cause an alert.

## 1.9.0 (Verwood)
- **Season leaderboards:** first Monday of each month, May to October, one carousel post: a club-wide
  board for all adult teams, then one per adult team (3+ games). Top 5 run scorers (innings, highest
  score), wicket takers (best figures) and catches & stumpings, season to date. Junior and indoor
  teams are left out. Scorecards are read once and cached. Settings under `leaderboards:`.
- The setup check previews the leaderboards from the latest outdoor season's real scorecards.
- Sponsor report email: subject set in club.yml (`report → email_subject`).

## 1.8.0 (Verwood)
- **Monthly sponsor report:** on the 1st of each month, a one-page PDF for the sponsor with last month's
  views, accounts reached, likes/comments/shares, followers (and change), the top three posts and how
  many posts and Stories carried their logo. Opened as an issue (label *report*) to forward on; never
  posted. Run it for any month from **Actions → Sponsor report**. Needs the Meta token to include
  `read_insights` and `instagram_manage_insights`; the setup check says if it doesn't.

## 1.7.0 (Verwood)
- **Club news and events:** Issues → New issue → *Club news or event*. Fill in a headline, details and
  (optionally) a date, time, venue, link, photo and a "post on" date. The kit makes a branded post and
  Story and opens it for approval. News is always previewed first, even with automatic posting.
- Approved news with a "post on" date waits (label *scheduled*) and goes out with that morning's run.
- Events get a "Today" reminder Story on the morning of the event.
- Only people with access to the repository can use the form; anyone else's is ignored.

## 1.6.0 (Verwood)
- **Match photos as backgrounds:** match result, milestone and results summary posts use a photo from
  the private photo store's `match-photos` folders, darkened under the club blue. Each team has its own
  folder; `Indoor`, `Juniors` and `Club` cover everything else. Photos rotate (least recently used
  first), so they don't need to be from the game itself. Milestones with a player photo keep that
  instead. Without any photos, posts look as before. Settings under `match_photos:`.

## 1.5.0 (Verwood)
- **Matchday stories:** each morning there's a games day, one "Matchday" story goes to Instagram and
  Facebook Stories listing that day's senior games, home and away, with kick-off time, opponent and
  venue. No feed post. Home games with no ground on Play-Cricket show Potterne Park (indoor games
  don't get a guessed venue). Settings under `matchday:`.
- Daughters and Sons teams now count as junior teams.

## 1.4.0 (Verwood)
- **Milestone posts:** 50s, 100s and five-wicket hauls get a post (and story) of their own, made
  alongside the daily match post. Never repeated.
- **Player photos** (optional) from a private photo store: `adults/` and `juniors/` folders. Adults
  get photo and name; juniors follow ECB guidance and never get both (`milestones → junior_photos`).
  Photos are only ever drawn into the finished graphic and are never saved in this repository.

## 1.3.0 (Verwood)
- **Instagram and Facebook Stories:** each post can also go out as a tall 1080×1920 story, after the
  normal post (`posts → stories`). Busy weeks split across several story frames. A story that fails
  never affects the normal post, and a retry only re-does what didn't go out.

## 1.2.0
- **Shortened names for every team by default** (`juniors → apply_to_all_teams: true`). Juniors
  often play in adult, women's and family sides, so a team's name doesn't tell you a player's
  age. Every player is now shown as first name and initial ("Ben T."), or whatever
  `juniors → names` says. Set `apply_to_all_teams: false` to show full names for adult teams again.

## 1.1.1
- Copes with Play-Cricket briefly blocking requests: the kit waits and retries for a few minutes,
  only blames the API token when Play-Cricket really says it's wrong, and runs a second time
  each morning in case the first try couldn't get through. Nothing is ever posted twice.
- *Workflow change:* `make-posts.yml` has a second morning run. Copy it across if *Update kit* asks you to.

## 1.1.0
- **Your own pictures:** a background photo for all graphics or one per post type, with your club
  colour laid over it so text stays readable (`background_darkness`).
- **Sponsor:** a logo or name at the bottom of every graphic, and optionally in captions.
- **Your own wording:** post titles, "Victory"/"Defeat" and the other result words, and the
  fixtures sign-off.
- **Show or hide:** top performers, the toss line, grounds on fixtures, and your handle and website.
- **Own designs:** files in `my-templates/` replace the kit's (see `docs/OWN-DESIGNS.md`).
- **Update kit button:** get new versions from the Actions tab without losing your settings.
- Setup check lists the pictures and changes you're using, and warns about photos that would look blurry.

All new settings are optional. Existing `club.yml` files work unchanged.

## 1.0.0
- First release: fixtures, results round-up and match result posts from Play-Cricket, with
  approval through GitHub issues and posting to Facebook and Instagram.
