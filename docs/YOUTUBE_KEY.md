# Create the YouTube API key (automatic video search)

[Português](CHAVE_YOUTUBE.md) · **English**

The application only needs this key to **find the song's video on YouTube by itself**.
Without it, everything else works and you can paste the video address by hand.

It is free and does not ask for a credit card. Use a personal Google account (Gmail): company accounts
may have Google Cloud blocked.

## 1. Create a project

1. Open https://console.cloud.google.com and sign in with your Google account.
   The first time, accept the terms of service.
2. At the top of the page, click the project selector (next to "Google Cloud") and then
   **New project**.
3. Name: `PDF-to-GP5` (any name works). Click **Create** and wait a few seconds.
4. Check that the project selector at the top shows the new project.

## 2. Enable the YouTube Data API v3

1. Open https://console.cloud.google.com/apis/library/youtube.googleapis.com
   (or menu ☰ → **APIs & Services** → **Library** → search for "YouTube Data API v3").
2. Click **Enable**.

## 3. Create the key

1. Menu ☰ → **APIs & Services** → **Credentials**
   (https://console.cloud.google.com/apis/credentials).
2. **+ Create credentials** → **API key**. The key appears (it starts with `AIza…`).
   Click the copy icon.
3. Recommended: click **Edit API key** (or the key's name) → under
   **API restrictions** choose **Restrict key** → tick only **YouTube Data API v3** →
   **Save**. That way, if someone sees the key, it can only be used to search YouTube.

## 4. Put the key in the application

The key is kept in a text file in the project folder (the same one as `start.bat` / `start_env.bat`).
That file **does not go to git** (it is in `.gitignore`).

The easiest way: Settings → Server status → **Set up key**.

**With Notepad**
1. Open Notepad and paste the key (just the key, on one line).
2. **File → Save as…**, go to the project folder, for example
   `C:\Users\<user>\…\PDF-to-GP5`.
3. For **Save as type**, choose **All files (\*.\*)** and for **File name** type
   `youtube_api_key.txt`. Save.
   (Without "All files", Windows saves `youtube_api_key.txt.txt` and the application will not find it.)

**Or in a command prompt** (in the project folder; replace `AIza...` with your key, with no space before `>`):

```bat
echo AIza...> youtube_api_key.txt
```

## 5. Restart

Close the application page (the server closes by itself) and run `start.bat` / `start_env.bat` again.
After converting a song, the video panel opens by itself with the video it found.

## Check that it is connected

When it starts, the server window shows one of these lines:

- `Vídeo do YouTube: pesquisa automática ligada.` (YouTube video: automatic search on) — all good.
- `Vídeo do YouTube: pesquisa automática desligada (…)` (YouTube video: automatic search off) — the reason is in
  parentheses (file not found, empty, or the first line is not a key). The video panel shows the
  same reason. Notepad can save as UTF-8, UTF-8 with BOM or "Unicode": all of them work.

## The video shows as "unavailable"

- If the video's owner does not allow it to be watched outside YouTube, the application moves on by itself to the
  next search result. If none will play, it shows "The video's owner doesn't allow it to be watched outside YouTube":
  choose another video from the list, paste another address or use "Open the video on YouTube".
- If it happens with every video, the browser is blocking the YouTube player inside the page.
  This happens in **Brave** (it works in Chrome and Edge): turn off Shields for `127.0.0.1`
  (lion icon in the address bar → Shields at the bottom) and reload the page, or use
  Chrome/Edge (sometimes it does not play even with Shields off: use Chrome, which the startup
  scripts already open). In Brave the panel's own message reminds you of this. The application already tries the regular YouTube player when the "nocookie" one fails.

## Limits and problems

- The free quota allows about **100 searches per day**; each song is searched at most once
  a day (the server keeps the result), so that is plenty.
- "Automatic search is off" in the panel: the file was not found or the key is not in the
  right format. Check the file name (no `.txt.txt`) and that it contains only the key.
- "Could not search YouTube": no internet, the company network blocks
  `googleapis.com`, the API is not enabled in the project, or the day's quota has run out.
- You can disable or delete the key at any time under **Credentials**.
