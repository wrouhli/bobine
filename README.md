<div align="center">
  <sub>🌍 <a href="README.fr.md">Français</a> · <b>English</b></sub>
  <img src="assets/banniere.png" alt="Bobine: your saved videos become a local library, at home" width="820">
  <h1>🎞️ Bobine</h1>
  <p><b>Your saved Reels, and any TikTok or YouTube video, become a local knowledge base you can search and question. On your Mac or your server, at home.</b></p>
  <p>
    <a href="https://github.com/wrouhli/bobine/releases"><img src="https://img.shields.io/github/v/release/wrouhli/bobine?color=6C4DFF&label=version&style=flat" alt="Version"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT"></a>
    <img src="https://img.shields.io/badge/macOS%20%2B%20iPhone-black?logo=apple" alt="macOS + iPhone">
    <a href="linux/README.en.md"><img src="https://img.shields.io/badge/Linux%20%2F%20VPS-black?logo=linux" alt="Linux / VPS"></a>
    <img src="https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white" alt="Python 3.10+">
    <a href="https://github.com/wrouhli/bobine/actions/workflows/tests.yml"><img src="https://github.com/wrouhli/bobine/actions/workflows/tests.yml/badge.svg" alt="Tests"></a>
  </p>
  <p>
    <a href="https://github.com/wrouhli/bobine/stargazers"><img src="https://img.shields.io/github/stars/wrouhli/bobine?style=for-the-badge&label=%E2%AD%90%20Star%20this%20repo&color=6C4DFF&logo=github&logoColor=white" alt="⭐ Star this repo"></a>
  </p>
</div>

You share a video from your iPhone. A few minutes later, Bobine has downloaded it, transcribed it, summarized it and filed it into a card. In the evening, you open a little web page on your phone: everything is there, with search. **And everything stays at home.**

> **Two editions, the same vault:**
> 🍎 **Mac + iPhone**: you're in the right place. Download the folder, double-click, done (iCloud, notifications, Crush).
> 🐧 **Linux / VPS**: the server edition: installer, systemd wake-up, HTTPS page → **[linux/](linux/README.en.md)**

> **🇫🇷 Language:** Bobine speaks French for now: the installer, the pages and the notifications are in French. AI summaries are in French by default; English summaries are available as an optional setting below. *(A fully English onboarding is [on the way](https://github.com/wrouhli/bobine/issues/32).)*

> **📥 Just downloaded the folder?** Start with **"👉 1. LIS-MOI D'ABORD (installation)"**, a French page that walks you through the install click by click, macOS security questions included. Everything is also detailed in the [Installation](#installation) section.

---

## Contents

- [Overview](#overview)
- [How it works](#how-it-works)
- [What you need](#what-you-need)
- [Installation](#installation)
- [Your day-to-day Bobine](#your-day-to-day-bobine)
- [Importing an Instagram export](#importing-an-instagram-export)
- [The costs](#the-costs)
- [Troubleshooting: the classics](#troubleshooting-the-classics)
- [Uninstalling Bobine](#uninstalling-bobine)
- [Project structure](#project-structure)
- [FAQ](#faq)
- [Contributing](#contributing)
- [Author](#author)
- [License](#license)
- [Linux / VPS edition](linux/README.en.md)

## Overview

**Your Bobine page**: instant search, topic pills, cards with summaries:

![Your Bobine page: search, topics, cards](assets/capture-liste.png)

**The topic map**: the subjects of your collection, linked to one another:

![Bobine's topic map](assets/capture-carte.png)

**And you can ask it questions**: "Which videos talk about cooking?" The assistant reads your cards and answers *(see "ask your collection", in the installation section)*.

*(All these screenshots come from a demo Bobine.)*

## How it works

```
iPhone                        Mac                                    iPhone
──────                        ───                                    ──────
Share ──────────►  iCloud box ──►  every 15 minutes:               ┌► Files → iCloud Drive
  (Instagram,     (inbox.txt)       1. checks the box              │    → Bobine
   TikTok,                          2. downloads the audio          │    → vault.html
   YouTube…)                        3. local transcription          │      (search + summaries)
                                    4. summary (your API key)       │
                                    5. cards + page ────────────────┘
```

- **Local transcription** (Whisper): free. For YouTube, Bobine first fetches the **subtitles** (a few kilobytes, a matter of seconds) and only transcribes when there are none.
- **Summaries**: *optional*. With your own API key (DeepSeek, OpenAI, OpenRouter…), Bobine writes a concrete title, topics and summary for each card, updates the index and regenerates the pages.
- **Guardrails**: never a download burst (15 per run, at most 50 attempts a day, failed ones included), never two runs at once, a failure is retried only twice. A card whose summary failed stays on your page, marked "summary pending", and is retried at every run.

## What you need

- a **Mac** + an internet connection;
- **Python 3.10 or newer** (the install script guides you);
- **ffmpeg** (`brew install ffmpeg`);
- *(optional, recommended)* an **iPhone**, to share in one gesture;
- *(optional, recommended)* an **API key** for the summaries: [DeepSeek](https://platform.deepseek.com) is the cheapest (a few cents for hundreds of videos).

## Installation

Installation is **interactive**, guided from start to finish: you choose the **name** of your vault and **where** to install it, you paste your API key if you want summaries (optional), and Bobine does the rest (environment, dependencies, automatic wake-up).

1. **Download** this folder ("Code" → "Download ZIP"), then unzip it (double-click the `.zip`).
2. Open the downloaded folder and **start with "👉 1. LIS-MOI D'ABORD (installation)"** (a French page): it explains, click by click, the 2-3 macOS security questions (it's normal for macOS to ask, and it's actually healthy).
3. **Double-click "👉 2. Installer Bobine.command"** and answer the questions (name, location, optional API key).
4. If prompted: `brew install ffmpeg`.

> **🛡️ macOS dialogs, in short** (everything is illustrated with images in the page above): click **"Terminé"** (never "Placer dans la corbeille" / Move to Trash), then System Settings → **Privacy & Security** → "Open Anyway", then double-click the installer again.
>
> **Clicked "Placer dans la corbeille"?** No drama: right-click the file in the Trash → "Put Back", or unzip the ZIP again.

**If you prefer the Terminal**, you can run the installer yourself. Read the script before authorising it; security prompts can vary with your Mac settings. Move into the downloaded folder (tip: type `cd` followed by a space, then drag the folder into the Terminal window, and press Enter), then run:

```bash
./install.sh    # banner, guided questions, environment + dependencies...
```

At the end, everything lives in **your vault folder** (the one you chose): if you installed into a separate folder, the downloaded folder is no longer needed. If you chose to keep Bobine in the downloaded folder, keep that folder.

*(Optional check, in your vault folder: `.venv/bin/python enrichir.py --dry-run`.)*

### *Optional*: the API key for summaries

Open `config.env` (created by the installation) and paste your key on the right line:

```
DEEPSEEK_API_KEY=sk-…
```

That's it. The other lines stay empty.

If a summary is delayed, your video is still saved. Bobine will try again automatically. You don't need to watch it or restart it.

<details>
<summary>Other AI providers and advanced settings (optional)</summary>

Other providers work too, each with its own line:

| Provider | Line in `config.env` | Model |
|---|---|---|
| DeepSeek | `DEEPSEEK_API_KEY=…` | `deepseek-chat` by default; change it with `API_MODEL=…` |
| OpenAI | `OPENAI_API_KEY=…` | `API_MODEL=…` required (e.g. `gpt-4o-mini`) |
| OpenRouter | `OPENROUTER_API_KEY=…` | `API_MODEL=…` required |
| Google Gemini | `GEMINI_API_KEY=…` | `API_MODEL=…` required |
| Any OpenAI-compatible service | `API_KEY=…` + `API_BASE_URL=…` | `API_MODEL=…` required |

For summaries in English, add `LANGUE_RESUMES=en` to `config.env`. The interface remains in French. DeepSeek's existing default is kept; if your provider stops accepting a model, you can choose another with `API_MODEL=…`.

</details>

### *Optional*: your profile (the "For you" block)

With an API key, each card gets a **Memo** tab (the main idea, key points, steps, tools mentioned) and a **Key takeaways** box. If you also describe yourself in a few lines, each card adds a **For you** block: what this video brings *you*.

The installer asks the question once (press Enter to skip). You can write or change it at any time in `Mon profil.txt`, in your vault folder: a few lines about what you do and what you look for in your videos. Lines starting with `#` are ignored. Older videos get their memo gradually, 10 per run, without touching their existing summaries.

### *Recommended*: the iPhone shortcut (share in one gesture)

On your iPhone, in the **Shortcuts** app:

1. **+** → add the **"Append to Text File"** action (search for "append");
2. in the text field: insert the **"Shortcut Input"** variable;
3. **File Path**: type exactly `inbox.txt` (leave the location "Shortcuts" on iCloud Drive);
4. enable the **"New Line"** option if it appears;
5. ⓘ → enable **"Show in Share Sheet"**, type: URLs only;
6. name it **"Send to Bobine"**.

Usage: in Instagram/TikTok/YouTube → **Share → Send to Bobine**. That's it.

### *Recommended*: ask your collection (Crush)

[Crush](https://charm.sh/crush) is an assistant that lives in the Terminal: light, open source, no account to create. It uses **the same API key as your summaries**; and since it launches inside your vault folder, it reads your cards to answer.

![Ask your collection: the assistant reads your cards and answers](assets/capture-crush.png)

```bash
cd ~/Bobine    # your vault folder
crush
```

Then ask questions in plain language: "Which videos talk about cooking?", "Summarize the video about editing", "Any ideas for a post?"… *(example in the image above, from a demo Bobine.)*

*(The installation prepares everything: the folder's `.crushrc` file holds your key, the DeepSeek model and read-only access. Crush can read and search your cards, but its tools for editing files, running commands or going online are removed. Not installed yet? `brew install charmbracelet/tap/crush`; the install script offered to do it for you.)*

## Your day-to-day Bobine

- **On the Mac**: **double-click "Ma page"** in your vault folder (or open `vault.html`): search, topic pills, links to the videos.
- **On the iPhone**: Files → iCloud Drive → **Bobine** → `vault.html` (updated with every new batch; the graph map stays on the Mac).
- **To ask questions**: run `crush` in your vault folder (see "ask your collection"), or simply read the cards: they are plain Markdown files in `raw/` (a `grep`, Obsidian…).

## Importing an Instagram export

*Advanced option*: to catch up on years of saves at once.

If your account holds hundreds (or thousands) of Reels kept "for later", ingesting everything in one go would mean hours of transcription for cards you would never re-read. **`filtre.py` lets you sort first**: it reads your export, applies your rules, and only the selected posts go to transcription. The sorting follows **your own collections**: your filing is the source of truth.

> 🛡️ **Low risk on the account side**: the export is requested via Instagram's official tool; `filtre.py` connects to nothing (everything is local); and the ingestion keeps its usual gentle pace (one video at a time, 15 per run, 50 attempts a day). No automated download is entirely risk-free, which is exactly why these limits exist.

**1.** On Instagram: **Settings → Accounts Center → Your information and permissions → Download your information** (**JSON** format). It arrives by email, sometimes within 48 hours.

**2.** Unzip the archive and store it somewhere of yours. You should see `saved_posts.json` and `saved_collections.json` in there.

**3.** In your vault folder, generate your sorting file, then check it:

```bash
cd ~/Bobine     # your vault folder
.venv/bin/python filtre.py --export "PATH/TO/instagram-my_account" --init-config
.venv/bin/python filtre.py --export "PATH/TO/instagram-my_account" --rapport
```

`--init-config` writes **`filtres.yaml`**, pre-filled with your collections: open it and switch to `false` anything you don't want landing in (memes, ads, quotes…). `--rapport` shows the outcome of your choices, pattern by pattern, with examples, **without running anything**. Posts that no rule classifies stay "to review": never lost, never ingested by surprise.

**4.** When the report looks right, produce the list and start transcription (in batches, as usual):

```bash
.venv/bin/python filtre.py --export "PATH/TO/instagram-my_account"
.venv/bin/python ingest.py liens-filtres.txt --vault . --cookies chrome --limite 10
.venv/bin/python enrichir.py --vault .     # summaries + pages
```

*(`filtres.yaml` stays with you: it is never published. You can also inspect it: `filtres.exemple.yaml` shows a complete, commented file.)*

## The costs

| Piece | Cost |
|---|---|
| Video downloads (yt-dlp) | Free |
| Transcription (Whisper, local) | Free |
| YouTube subtitles | Free |
| Summaries (your API key) | a few cents for hundreds of videos |

## Troubleshooting: the classics

- **A shared video hasn't appeared yet?** Give Bobine up to 15 minutes while your Mac is awake. Check that you used “Send to Bobine” when sharing.
- **“Résumé en attente”?** Your video is saved. Summaries are optional; if you enabled them and the service is busy, Bobine will retry automatically.
- **Today's limit reached?** New videos will be processed tomorrow. Summaries for videos already saved can continue today.

<details>
<summary>Advanced troubleshooting: logs, provider settings and manual commands</summary>

- **Nothing happens after a share** → check `logs/watch.log` (last run + errors). The wake-up runs every 15 minutes, and catches up when the Mac wakes.
- **"yt-dlp" errors** → Instagram and YouTube change often; updating fixes almost everything: `.venv/bin/pip install -U yt-dlp`
- **A post never goes through** → it is probably deleted or private (common on old saves): Bobine retries it only twice, then moves on.
- **Cards stay "(summary pending)" although you have a key** → open `logs/watch.log`: the provider's message says why (key refused, no credit, retired model). For a retired model, set `API_MODEL=…` in `config.env`; Bobine retries at every run.
- **A card with no text** → the video has no speech and no subtitles (music only). The card will keep the description only.
- **No alert when the wake-up gets stuck?** If the iCloud box becomes unreadable for ~1 h, a macOS notification is sent automatically.
- **Run it by hand** (for a batch, or after an import):

```bash
cd ~/Bobine        # your vault folder (the location you chose)
.venv/bin/python ingest.py liens.txt --vault . --cookies chrome --limite 10
.venv/bin/python enrichir.py --vault .     # summaries + pages
```


</details>

## Uninstalling Bobine

Stop Bobine from your library folder:

**Double-click "Désinstaller Bobine.command"** (or, in the Terminal: `./desinstaller.sh`).

It disables background services belonging to this library and offers to remove the iCloud page. **Your local videos and other files stay in place.** If you no longer want them, check the folder and delete it yourself; Bobine never deletes the library automatically. *(Crush, the assistant, is a separate tool: it stays installed if you want to keep it. And on your iPhone, you can delete the "Send to Bobine" shortcut.)*

## Project structure

Your vault folder (the one you chose at installation) looks like this:

```
Bobine/
├── ingest.py           # downloads + transcribes → cards (raw/)
├── filtre.py           # (optional) picks what to ingest from an Instagram export
├── enrichir.py         # summaries via your API key → index.md + pages
├── generate_page.py    # builds vault.html (readable without JavaScript) + the map
├── graphe.py           # (legacy) [[Topics]] links for Obsidian
├── watch.sh            # the wake-up: checks the box and chains everything
├── install.sh          # guided installation (environment, wake-up)
├── 👉 2. Installer Bobine.command   # double-click: (re)installs
├── desinstaller.sh     # stops background services; keeps local files
├── Désinstaller Bobine.command # double-click: uninstalls
├── requirements.txt    # Python dependencies
├── config.example.env  # copy to config.env (API key, settings)
├── config.env          # YOUR settings and API key (private, never in the repo)
├── .crushrc            # Crush settings for this folder (your key, read-only access)
├── filtres.yaml        # (if you import) your sorting rules, they stay with you
├── LICENSE
├── raw/                # YOUR cards (never in the repo)
├── memos/              # the memo of each video (with an API key; never in the repo)
├── Mon profil.txt      # (optional) a few lines about you, for "For you"
├── journal.json        # what has been processed (successes, failures, retries)
├── index.md            # the condensed index (summaries + topics)
├── vault.html          # the page to browse
├── Ma page.webloc      # double-click: opens the page in your browser
├── graph.html          # the topic map
└── logs/               # logs (watch.log)
```

## FAQ

**What about Windows or Linux?**
Windows: no. Bobine is designed and tested for Mac + iPhone, and that's a deliberate choice. **Linux: yes.** A complete Linux/VPS edition exists (installer, systemd wake-up, HTTPS page, local inbox) → **[linux/](linux/README.en.md)**. Same core, same license, same philosophy: everything at home.

**Where does my data go?**
Bobine keeps your knowledge base on your machine: no account, no server of ours, no telemetry. A few things do leave your machine, all transparent: the video downloads from Instagram, TikTok and YouTube (like any downloader), using your browser's login cookies for Instagram and TikTok only (on the Mac, Chrome by default: macOS may ask once for access to "Chrome Safe Storage"; change it with `COOKIES=…`); the one-time downloads of the Python dependencies and the transcription model; and, only if you turn on the AI features (summaries, asking questions with Crush), the relevant texts (transcripts, cards, your questions, your profile if you wrote one) sent to the provider you chose (DeepSeek, OpenAI, OpenRouter…) with your own API key. On the Mac edition, the generated page can also be synced through iCloud (offered at installation, you can decline it).

**What if I don't use an API key?**
Everything runs fine: each card is still created with its transcription and description, in `raw/`, and it appears on your page right away, marked "(summary pending)". Add a key whenever you want: at the next run (within 15 minutes), Bobine replaces the pending entries with real summaries and topics, automatically.

**How is it different from Obsidian or Notion?**
It is not a replacement: Bobine **builds** your library. The cards are plain Markdown files (`raw/`), which you can open with any tool, including Obsidian.

**Which apps does it work with?**
Instagram (Reels), TikTok and YouTube links, shared from your iPhone or pasted anywhere.

## Contributing

Feedback and contributions are welcome: the project was kept simple on purpose:

- **A bug, an idea?** → open an [issue](https://github.com/wrouhli/bobine/issues).
- **A fix?** → a direct pull request, no ceremony (details: [CONTRIBUTING.md](CONTRIBUTING.md)).
- **A typo in this English version?** → welcome, just tell us in an issue.

And of course: **a ⭐ on the repo** helps other people discover Bobine.

## Author

Created and maintained by **[Wahid Rouhli](https://www.wahidrouhli.com/)**.

## License

MIT: see `LICENSE`.
Thanks also to [yt-dlp](https://github.com/yt-dlp/yt-dlp), [faster-whisper](https://github.com/SYSTRAN/faster-whisper), [gallery-dl](https://github.com/mikf/gallery-dl) and [Charm](https://charm.sh).
