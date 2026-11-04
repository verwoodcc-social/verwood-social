# Your own graphic designs (for the technically minded)

Most clubs don't need this. The settings in `club.yml` cover badge, colours, photos, sponsor,
wording and what to show. If you know a little HTML and CSS, you can go further.

## Small style changes: `my-templates/extra.css`

Create a folder called `my-templates` with a file `extra.css`. Anything in it is added after the
kit's own styles, for example:

```css
.title { letter-spacing: 0; }          /* tighter headings */
.row { border-radius: 8px; }           /* squarer boxes */
.verdict.W { color: #FFD400; }         /* yellow "Victory" */
```

## Whole designs: copy and edit a template

Copy any of these from `kit/templates` into `my-templates` and edit your copy:

| File | What it draws |
|---|---|
| `list.html` | the fixtures and results round-up graphics |
| `match.html` | the single match result graphic |
| `base.css` | the shared styles (fonts, sizes, boxes, background) |
| `_foot.html` | the footer: handle, website, sponsor and page number |
| `_photo.html` | the background photo layer |

Your copies are used instead of the kit's. They're [Jinja](https://jinja.palletsprojects.com/)
templates, and the graphics are 1080 × 1350 pixels.

**Your designs survive kit updates.** The *Update kit* workflow never touches `my-templates`. If
a new kit version adds something to a template you've copied, you'll need to add it to your copy
yourself. `docs/CHANGES.md` lists what changed.

Saving anything in `my-templates` runs **Check setup**, which opens a preview so you can see the result.
