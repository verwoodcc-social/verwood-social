# What's new

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
