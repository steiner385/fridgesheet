# Fridge Sheet on Linux: quick start

Fridge Sheet prints your kids' open schoolwork every school day and shows it in a small web
app on your own machine. This page gets it running on a Linux desktop or a home server in
about 20 minutes, using a terminal for the install and the web app for everything after.
You don't need to know Python. Nothing about your kids leaves your computer.

## What you need

- A Linux machine with Python 3.11 or newer (`python3 --version`), `git`, and a terminal.
  It has to be on at the time you want the sheet to print.
- Your district's OneLogin **parent** username and password, the ones you use for Canvas and
  Home Access Center. If OneLogin texts you a code every time you sign in, the automatic
  refresh cannot work.
- A printer set up in CUPS (it shows in `lpstat -a`), if you want the sheet printed.
- On a desktop: the GNOME keyring and `secret-tool` (on Debian and Ubuntu, the
  `libsecret-tools` package), which hold the password. On a server with no desktop, see step 2.

The app comes set up for Lakota Local Schools. For another district, see
[Another school district](user-guide.md#24-another-school-district) in the user guide first.

## 1. Install

```bash
git clone https://github.com/steiner385/fridgesheet ~/fridgesheet
cd ~/fridgesheet
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
playwright install chromium
```

On a minimal or server install, also run `playwright install-deps chromium` (it asks for
sudo) so the browser the app signs in with has its libraries.

Then start the app in the background, so it is always there and comes back after a reboot:

```bash
fridgesheet service install
```

Open <http://127.0.0.1:8433/> in a browser on the same machine.

## 2. Where the password goes

- **On a desktop** you type it on the Settings page in step 3, and it goes into your GNOME
  keyring.
- **On a server with no desktop** the keyring stays locked, so put the login in a file only
  you can read instead, and let the app keep running while you're signed out:

  ```bash
  mkdir -p ~/.fridgesheet
  nano ~/.fridgesheet/.env
  ```

  Put these two lines in it, with your own login, and save:

  ```
  FRIDGESHEET_ONELOGIN_USERNAME=your-username
  FRIDGESHEET_ONELOGIN_PASSWORD=your-password
  ```

  Then:

  ```bash
  chmod 600 ~/.fridgesheet/.env
  loginctl enable-linger "$USER"
  systemctl --user restart fridgesheet-web
  ```

  The password sits in that file in plain text. The user guide's
  [server section](user-guide.md#23-a-server-with-no-desktop-linux) has a 1Password option
  instead. To open the web app from your laptop, run `ssh -L 8433:127.0.0.1:8433 yourserver`
  there and open <http://127.0.0.1:8433/> on the laptop.

## 3. Set it up

1. When the app asks **Who's looking?**, click **A grown-up**.
2. Click **Settings** in the list on the left. Under **School login**, type your OneLogin
   username and password, then click **Save** at the bottom. (On a server using `.env`, the
   card says the login comes from the environment; skip to the next step.)
3. Click **Test login** and wait up to a minute. Both lines should say **OK**. If not,
   check the username and password, **Save**, and try again.
4. Click **Today**, then **Refresh now**. The first refresh takes 1 to 3 minutes; then each
   of your kids appears.
5. Back on **Settings**, under **Printing and the report window**, pick your **Printer** and click **Save**.
6. Click **Schedules**.
   - Under **Refresh the data**, tick **Refresh on a schedule** and click **Save**. This keeps
     everything up to date.
   - Under **Open Work Sheet**, tick **Run this on a schedule**, set the **Time** (it is a
     24-hour clock, so 2 pm is **14:00**), tick the school days, tick **Print it**, and
     click **Save**.

That's it. The sheet prints on its own at the time you chose, and the app shows the same
list any time you open it.

## Phones and tablets

To open the app from other devices at home, tick **Allow other devices on this network** on
Settings, click **Save**, and run `systemctl --user restart fridgesheet-web`. Settings then
shows the address and a QR code. The app has no password of its own, so only do this on a
network you trust. The user guide's [phone section](user-guide.md#16-using-it-on-a-phone-or-tablet)
has more.

## Updating

There is no update button on Linux; the downloads on the releases page are Windows
installers. To update:

```bash
cd ~/fridgesheet
git pull
. .venv/bin/activate
pip install -e .
systemctl --user restart fridgesheet-web
```

The header may say a newer version *is available* even right after you update. That
notice compares against the Windows release numbers, so you can ignore it once `git pull`
says you're up to date.

## If something goes wrong

- **Diagnostics** (in the list on the left) checks everything and says what failed. From
  the terminal, `fridgesheet doctor` does the same.
- **Runs** shows every sheet the app built or printed, with a **Reprint** button.
- `journalctl --user -u fridgesheet-web` shows the web app's log.
- **Help** (also in the list on the left) opens the full [user guide](user-guide.md);
  [Troubleshooting](user-guide.md#20-troubleshooting) covers the usual problems.

To remove it: untick the schedules on **Schedules**, run `fridgesheet service remove`, then delete `~/fridgesheet`. Your data is in
`~/.fridgesheet`; delete that too if you don't want to keep it.
