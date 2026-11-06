# Setting up the Cricket Social Kit for your club

This takes about **an hour and a half**, spread over a few days because the Play-Cricket
token can take a while to arrive. You don't need to know any coding. Everything happens in
your web browser.

**You'll need:**
- a free **GitHub** account ([github.com/signup](https://github.com/signup)), ideally made with a club email address
- admin access to your club's **Facebook Page**
- your club's **Instagram** account switched to a *professional* account and linked to the Facebook Page
  (in Instagram: *Settings → Account type and tools*)
- a **committee member** who can sign Play-Cricket's API agreement for the club

When it's running, every morning GitHub checks Play-Cricket and makes the graphics. It sends
each post to you for approval, and when you approve it, it posts to Facebook and Instagram.

---

## Step 1 · Make your club's copy (5 minutes)

1. Sign in to GitHub and open the kit's page.
2. Click the green **Use this template** button, then **Create a new repository**.
3. Give it a name, e.g. `ourclub-social`.
4. Choose **Public**. Instagram can only fetch the images if the repository is public.
5. Click **Create repository**.
6. In your new repository go to **Settings → Actions → General**. Under *Workflow permissions*
   choose **Read and write permissions** and click **Save**.

## Step 2 · Add your club's details and badge (10 minutes)

1. **Badge:** open the `assets` folder, click **Add file → Upload files**, and upload your badge.
   An SVG or a PNG with a see-through background looks best.
2. **Settings:** open `club.yml` and click the ✏️ pencil to edit it. Fill in each section:
   - your club's name, and a short name for captions
   - your **Play-Cricket Site ID**. It's in small print at the very bottom of every page of your
     club's Play-Cricket site: *"Site ID 1234"*
   - your club's name **exactly as Play-Cricket writes it** in fixtures, e.g. `Verwood CC`
   - your badge's file name, e.g. `assets/our-badge.png`
   - your two club colours as hex codes. Search "colour picker" online if you need to find them.
     The kit uses the darker colour as the background.
   - which days to post fixtures and the results round-up
3. Click **Commit changes**.

Keep text in "quotes", and keep the spaces at the start of each line as they are.

## Step 3 · Get your Play-Cricket API token (a few days)

Play-Cricket gives each club its own token for reading its own data.

1. A **main admin or committee member** contacts the Play-Cricket help desk and asks for API
   access for the club's site. See ECB's page *"Do You Have an API to Access Play-Cricket Data?"*
   on the Play-Cricket help centre. They'll sign a short agreement for the club.
2. When the token arrives, go to your repository's **Settings → Secrets and variables → Actions**.
3. Click **New repository secret**.
4. Name it `PLAYCRICKET_API_TOKEN`, paste the token in, and click **Add secret**.

Secrets are hidden. Nobody, including you, can read them back, and they never appear in posts or logs.

## Step 4 · Connect Facebook and Instagram (about 45 minutes, once)

You'll make a **token** that lets the kit post to your Page and Instagram. Meta sometimes
renames these menus, so if something isn't exactly where described, look for the nearest match.

**4a. Check your Page and Instagram are in a Meta business portfolio**
1. Go to [business.facebook.com](https://business.facebook.com) → **Settings**. If you've used Meta
   Business Suite or run ads, the club probably has a business portfolio already. If not, create one.
2. In **Accounts → Pages**, check your club's Facebook Page is listed. Add it if not.
3. Click the Page, then the **Connected assets** tab. Your club's Instagram account should be listed.
   If it isn't, link it in Instagram (*Settings → Account type and tools*) or Meta Business Suite.

**4b. Register as a Meta developer and create an app**
1. Go to [developers.facebook.com/apps](https://developers.facebook.com/apps). If you see a welcome page
   instead of "My Apps", click **Get Started** and follow the steps: accept Meta's terms, confirm your
   email or phone, and pick any occupation.
2. Click **Create app**. Name it e.g. "Our Club Social Kit" and use your club email.
3. Choose the use case **Manage everything on your Page**, and also add
   **Manage messaging & content on Instagram**.
4. When asked, connect it to your club's business portfolio, then finish creating the app.
5. Switch on the permissions the kit needs. In the app, open **Use cases**:
   - next to *Manage messaging & content on Instagram*, click **Customize** and click **Add** next to
     `instagram_basic`, `instagram_content_publish` and `pages_read_engagement`
   - switch to *Manage Pages* (the use case switcher at the top) and click **Add** next to `pages_manage_posts`

**4c. Make a system user and its token**
1. Back in [business.facebook.com](https://business.facebook.com) → **Settings → Users → System users**,
   click **Add**. If **Add** is greyed out, the app from 4b isn't in your business portfolio yet.
   Name it e.g. "Social Kit", give it the **Admin** role, and create it.
2. With the system user selected, click **Assign assets** and give it **full control** of:
   - **Apps:** your new app
   - **Facebook Pages:** your club's Page

   You don't need to add the Instagram account. If it says "*(your Page)* shares these permissions",
   it gets access through the Page. If it asks you to log in to Instagram, you can skip that.
   If several people have full control of your portfolio, Meta may ask one of them to approve this.
3. Click **Generate token**, choose your app, and set **Token expiration** to **Never**.
4. Tick these permissions:
   `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`,
   `instagram_basic`, `instagram_content_publish`, `business_management`
5. Click **Generate token** and copy it. You only see it once.

**4d. Save it**
- In your GitHub repository, go to **Settings → Secrets and variables → Actions → New repository secret**.
  Name it `META_TOKEN`, paste the token, and click **Add secret**.
- Don't paste this token anywhere else, such as an email or chat. Anyone who has it can post to
  your club's Facebook and Instagram.

## Step 5 · Check everything works (5 minutes)

1. In your repository, click the **Actions** tab. If asked, click
   **I understand my workflows, go ahead and enable them**.
2. Click **Check setup** on the left, then **Run workflow → Run workflow**.
3. When it finishes, open the run and read the **Summary**. Each line has a ✅ or a ❌ with what to fix.
4. Open the **Issues** tab. There's a *Preview* issue showing sample graphics in your colours.
   This preview can't be posted.

When everything is ✅, the kit starts on its own the next morning.

## Step 6 · Day to day: approving posts

- Install the **GitHub** app on your phone and sign in.
- On your repository, tap **Watch → All activity**, so you're notified when a post is ready.
- Each post arrives as an **issue** with the graphics and the caption.
  - **To post it:** add the **approved** label (in the app, open the issue and tap *Labels*).
  - **To change the words:** edit the issue and change the text in the caption box, then approve.
  - **To skip it:** close the issue.
- Once posted, the issue is closed with links to the Facebook and Instagram posts.
- If posting fails, the issue explains why. Fix it, then add **approved** again.
  Anything already posted won't be posted twice.

**Letting others approve:** go to **Settings → Collaborators → Add people** and invite other
volunteers. Only people you add can approve posts.

## Step 7 · Make it your own (optional)

Everything below is optional, and all of it is done the same way: upload a picture and/or change
a line in `club.yml`. Each change opens a fresh **Preview** issue so you can see the result.

| You want to… | Do this |
|---|---|
| Use a photo of your ground as the background | Upload it to `assets`, then set `background_image: "assets/ground.jpg"` |
| Use a different photo for match results | Set `match_background:` (or `fixtures_background:` / `results_background:`) |
| Make the words easier to read on a busy photo | Set `background_darkness: strong` |
| Show a sponsor | Upload their logo and set `sponsor_logo:`, or just set `sponsor_text: "Their Name"` |
| Thank the sponsor in captions too | Set `sponsor_in_captions: true` |
| Change "Victory", "This Week's Fixtures" and so on | Edit the lines under `wording:` |
| Hide top performers or the toss | Set them to `false` under `show:` |
| Show the ground on fixtures | Set `ground_on_fixtures: true` under `show:` |

There's a step-by-step guide to uploading pictures in **`assets/HOW-TO-UPLOAD.md`**. Anyone
comfortable with HTML and CSS can go further with **`docs/OWN-DESIGNS.md`**.

---

## Good to know

**Changes and improvements** are made directly in this repository (it's Verwood's own copy; there's no separate template any more).

**What gets posted and when.** Every morning: one post per match played *yesterday* that has a
result and a scorecard. On your fixtures day: the next 7 days' fixtures. On your round-up day:
the previous 7 days' results. Matches whose scorecard is entered late are still in the round-up.
Set `lookback_days: 2` or `3` in `club.yml` to also give them their own post.

**Run it now.** On the **Actions** tab, click **Make posts → Run workflow**, choose which posts
to make, and click **Run workflow**.

**Players' names.** Graphics and captions show every player as first name and surname initial
("Ben T."), in every team. That's because juniors often play in adult, women's and family sides,
so a team's name doesn't tell you a player's age. You can change this in `club.yml` under
`juniors`: `names` can be `initial`, `first`, `full` or `none`. Setting `apply_to_all_teams: false`
gives full names in adult teams and keeps the rule only for junior teams (names like *U11*,
*Under 13* or *Girls*).

**Privacy.** The repository is public, so the graphics in the `posts` folder can be seen by
anyone who finds them, including ones you haven't approved yet. They only contain what's
already public on your Play-Cricket site. Your tokens stay secret.

**Out of season.** Nothing is posted when there are no matches. If GitHub ever emails to say
the schedule was paused for inactivity, open **Actions → Make posts** and click **Enable workflow**.

**Turning on automatic posting.** Set `approval: automatic` in `club.yml`. Posts then go straight
out without waiting for approval. An issue is still kept as a record of each one.

**If your posts are only visible to you.** Open your Meta app at developers.facebook.com, and
switch it from *Development* to **Live** (top of the page). Meta asks for a privacy policy link:
you can use the link to this repository's `docs/PRIVACY.md`.
