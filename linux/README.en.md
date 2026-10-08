# Bobine: Linux edition (server or VPS)

<sub>🌍 <a href="README.md">Français</a> · <b>English</b></sub>

**Your saved Reels, and any TikTok/YouTube video, become a local knowledge base you can search and question. On your machine, at home.**

The Linux/VPS edition of the [Bobine](https://github.com/wrouhli/bobine) project: it lives in the `linux/` folder of the repository and shares its core (ingestion, transcription, summaries, pages) with the Mac edition. Here, Bobine lives on a server: a small VPS, a machine at home, an old Linux laptop. No iCloud, no double-click: a systemd timer, an instant run when a link arrives, and a local inbox.

> **Status: first port.** The core (ingestion, transcription, summaries, pages, map) is the same code as the Mac version; only the installation and the wake-up differ. Tested primarily on Debian (aarch64 included).

## How it works

    links → inbox.txt → wake-up (right away, otherwise 15 min) → cards (raw/) → summaries → vault.html

1. You drop a link into `inbox.txt` (by hand, over `ssh`, or via the small optional HTTP server);
2. As soon as a link lands in the inbox (otherwise every 15 minutes, as a safety net), Bobine checks it: downloads, transcribes, writes a card into `raw/`;
3. With an API key: summary + topics → `index.md`;
4. `vault.html` (list) and `graph.html` (topic map) are regenerated.

*Without an API key: cards appear on the page right away, marked "(summary pending)", and Bobine replaces them with real summaries as soon as you add a key.*

## Requirements

- Linux with systemd (Debian 12+/Ubuntu 22.04+ and friends; aarch64 ok);
- Python 3.10+ with venv: `sudo apt install python3 python3-venv` (recent Debian: the versioned package, e.g. `python3.13-venv`);
- ffmpeg: `sudo apt install ffmpeg`;
- ~2 GB free (the transcription model downloads on the first run).

## Installation

Copy the folder to the server, then run the installer:

    rsync -av ~/bobine-linux/ my-server:~/bobine-linux/     # or scp -r
    ssh my-server
    cd ~/bobine-linux && ./install-linux.sh

The installer guides you: vault name, location, API key (optional), systemd wake-up. It never asks for root rights, except if you accept installing ffmpeg via apt.

## Sending a link

Three ways, all writing into the same inbox (`inbox.txt`):

**1. Directly on the server:**

    echo 'https://www.instagram.com/reel/Cxyz123AbCd/' >> ~/Bobine/inbox.txt

**2. From your computer, over ssh:**

    ssh my-server "echo 'https://youtu.be/jNQXAC9IVRw' >> ~/Bobine/inbox.txt"

**3. Over HTTP, from anywhere (optional link server):** see the next section.

Anything already processed is ignored automatically: old links can stay in the inbox.

## The wake-up

    systemctl --user list-timers bobine-watch.timer   # next run
    systemctl --user start bobine-watch.service       # trigger it right now
    tail -f ~/Bobine/logs/watch.log                   # what's happening

No need to wait for the next quarter hour: as soon as a link is pushed or
dropped into the inbox, the wake-up runs right away (systemd unit
`bobine-watch.path`, enabled at install time). The 15-minute timer stays as a
safety net (a drop while a run is in progress, a reboot...). Status:
`systemctl --user status bobine-watch.path`

Without systemd (or if in doubt), the cron equivalent:

    */15 * * * * /bin/bash ~/Bobine/watch-linux.sh >/dev/null 2>&1

## The link server (optional)

A tiny HTTP server (Python standard library, zero dependencies) that accepts your links over POST: handy from a phone shortcut:

    cd ~/Bobine
    openssl rand -hex 16                     # create a token…
    # … put it in config.env:  INBOX_TOKEN="…"
    .venv/bin/python inbox_server.py --vault ~/Bobine

Test (the server listens on 127.0.0.1:8785 by default):

    curl -X POST -H "Authorization: Bearer ***" \
         -d 'https://youtu.be/jNQXAC9IVRw' http://127.0.0.1:8785/push

To use it remotely, expose it properly via your tunnel (Cloudflare Tunnel, Tailscale) or a password-protected proxy (Caddy, nginx): **never this port in the open on the internet**. A systemd service template is provided in `systemd/bobine-inbox.service`.

## Viewing the page

`vault.html` (and `graph.html`) live in the vault folder. A few options:

    # read it from your workstation, through an ssh tunnel
    ssh -L 8080:127.0.0.1:8080 my-server
    # (on the server: cd ~/Bobine && .venv/bin/python -m http.server 8080 --bind 127.0.0.1)
    # → then http://127.0.0.1:8080/vault.html

Or simply bring the file over: `scp my-server:~/Bobine/vault.html .`

**Remotely, with a password:** `page_server.py` serves ONLY `vault.html` and `graph.html` (never your cards or your config), protected by a password:

    cd ~/Bobine
    openssl rand -hex 16                     # create a password…
    # … put it in config.env:  PAGE_PASSWORD="…"
    .venv/bin/python page_server.py          # listens on 127.0.0.1:8786

Combined with a tunnel (Cloudflare Tunnel, Tailscale…), the page becomes an address you can reach from anywhere, phone included. systemd service templates provided: `systemd/bobine-page.service` (the page) and `systemd/bobine-tunnel.service` (the dedicated Cloudflare tunnel). The script `activer-page-web.sh my-domain.tld` automates the whole setup (password, dedicated tunnel, services), without sudo.

Protected by Cloudflare Access (or another gatekeeper upstream)? Start the page with `--sans-mot-de-passe`: Cloudflare is the door, and the page no longer asks for anything (add the option to the ExecStart line of your service).

## Crush (bonus)

[Crush](https://charm.sh/crush) is an AI assistant for the terminal: launched in the vault folder, it reads your cards to answer ("Which videos talk about cooking?"). The installer prepares its settings file (`.crushrc`, read-only, with your key); you only need to install it, from the Charm repository:

    sudo mkdir -p /etc/apt/keyrings
    curl -fsSL https://repo.charm.sh/apt/gpg.key | sudo gpg --dearmor -o /etc/apt/keyrings/charm.gpg
    echo "deb [signed-by=/etc/apt/keyrings/charm.gpg] https://repo.charm.sh/apt/ * *" | sudo tee /etc/apt/sources.list.d/charm.list
    sudo apt update && sudo apt install crush
    # then, in the vault folder:  crush

## Maintenance

- **Update yt-dlp** (Instagram breaks often): `.venv/bin/pip install -U yt-dlp`
- **Instagram cookies**: if downloads fail, export a `cookies.txt` (extension "Get cookies.txt LOCALLY") from your desktop browser, copy it to the server, and point `COOKIES=` at it in `config.env`. YouTube works without cookies.
- **Slow transcription?** That's normal on a small server: every video goes through Whisper (the "small" model), from a few dozen seconds to a few minutes depending on the machine. The ceilings (15 videos per run, 50 per day) smooth the load.

## Troubleshooting

- **Nothing happens** → `tail -50 ~/Bobine/logs/watch.log`; check the inbox (`ls -la ~/Bobine/inbox.txt`) and the timer (`systemctl --user list-timers`).
- **Summaries don't come through** → no API key in `config.env` (optional; check with `.venv/bin/python enrichir.py --dry-run`).
- **systemd --user unavailable** → use the cron line above.
- **Dependency install fails** → `logs/install.log`; on small machines, some package builds need a system package (`sudo apt install build-essential python3-dev`).

## Uninstalling

    ./desinstaller-linux.sh     # removes the wake-up, the link server, and (if you want) the folder

## Differences from the Mac version

| | Mac | Linux (here) |
|---|---|---|
| Wake-up | launchd | systemd (or cron) |
| Inbox | iPhone shortcut + iCloud | `inbox.txt` (ssh, echo, HTTP) |
| Notifications | macOS Notification Center | `NOTIF_CMD` option (ntfy, etc.) |
| Page on phone | iCloud copy | URL served by your machine (tunnel/proxy) |
| Installation | double-click `.command` | `./install-linux.sh` |

The rest (ingestion, Instagram import filter, transcription, summaries, pages, map) is the same code as Bobine for Mac.

---

Bobine, written and directed by Wahid Rouhli · [github.com/wrouhli/bobine](https://github.com/wrouhli/bobine)
