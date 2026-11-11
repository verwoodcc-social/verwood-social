# Weekly backup to SharePoint

Every Sunday at about 03:40 (UK winter time) the **Weekly backup** workflow saves two files to the club
SharePoint, in **Verwood CC Club Documents → Documents → Social media kit backups → <date>**:

- `verwood-social-<date>.bundle`: the whole kit, with its settings, career data, saved state and history.
- `verwood-player-photos-<date>.bundle`: the private photo store, with its history.

The newest 8 weeks are kept (club.yml → backup → keep). Older weeks go to the SharePoint recycle bin,
where they can be restored for 93 days. If a backup fails, the committee gets an email.

The photo store backup sits in the club SharePoint, so keep that site's sharing limited to the committee.

## One-off setup: let the Microsoft 365 app save to that one site

The kit already uses the "Verwood social kit" app in Microsoft Entra to send emails. It needs one more
permission, limited to the Club Documents site only.

1. **Add the permission.** Microsoft Entra admin centre → App registrations → All applications →
   **Verwood social kit** → API permissions → Add a permission → Microsoft Graph → **Application
   permissions** → tick **Sites.Selected** → Add permissions → **Grant admin consent for Verwood Cricket
   Club** → Yes.
2. **Give it write access to the site.** Open [Graph Explorer](https://developer.microsoft.com/graph/graph-explorer)
   and sign in as a Microsoft 365 admin. If asked, consent to **Sites.FullControl.All** (Modify
   permissions tab).
   - Run `GET https://graph.microsoft.com/v1.0/sites/verwoodcc.sharepoint.com:/sites/VerwoodCCClubDocuments`
     and copy the `id` from the response.
   - Run `POST https://graph.microsoft.com/v1.0/sites/<that id>/permissions` with this request body:

     ```json
     {"roles": ["write"],
      "grantedToIdentities": [{"application": {"id": "2ee46bd1-ff58-443a-bb05-ed8199098908",
                                               "displayName": "Verwood social kit"}}]}
     ```
     A `201 Created` reply means it worked.
3. **Test it.** GitHub → Actions → **Weekly backup** → Run workflow. The run summary lists the files saved.

## Restoring from a backup

1. Download the `.bundle` file from SharePoint.
2. On any computer with git: `git clone verwood-social-<date>.bundle verwood-social`
3. Make an empty repository (GitHub, Azure DevOps or anywhere), then in the new folder:
   `git remote set-url origin <new repository address>` and `git push -u origin --all`
4. Add the secrets again (SETUP.md): they're never in the backup.
