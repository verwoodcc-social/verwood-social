# Adding your own pictures

This folder holds your club's pictures: your badge, and optionally background photos and a
sponsor logo. You don't need any technical knowledge. It works like attaching a file to an email.

## 1. Upload the picture

1. Open this `assets` folder on GitHub (you're probably looking at it now).
2. Click **Add file → Upload files**.
3. Drag your picture in, or click *choose your files*.
4. Click **Commit changes**.

**Tips for good results**
- **Background photos:** use a landscape or portrait photo at least **1080 pixels** on each
  side. Most phone photos are fine. Busy or bright photos look best with
  `background_darkness: strong`.
- **Badges and sponsor logos:** a PNG with a see-through background looks best. Logos are
  shown on a small white panel, so dark logos work well.
- **Use simple file names** with no spaces, e.g. `ground.jpg` or `sponsor.png`.
- JPG and PNG both work. Keep each file under 15 MB.

## 2. Tell the kit to use it

1. Go back to the main page and open `club.yml`.
2. Click the ✏️ pencil to edit.
3. Find the matching line and put `assets/` and the file name inside the quotes, for example:

   ```yaml
   background_image: "assets/ground.jpg"
   sponsor_logo: "assets/sponsor.png"
   sponsor_text: "Smith & Sons Builders"
   ```

4. Click **Commit changes**.

## 3. See how it looks

Saving `club.yml`, or uploading a picture here, runs **Check setup** automatically. A few
minutes later a **Preview** issue appears in the **Issues** tab, showing sample graphics with your
pictures. If anything's wrong, such as a misspelt file name or a photo that's too small, the
check explains what to change in plain English. Open the run in the **Actions** tab to read it.

**To remove a picture,** set its line back to `""` in `club.yml`.
