# What's new

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
