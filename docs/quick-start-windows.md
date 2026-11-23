# Fridge Sheet on Windows: quick start

Fridge Sheet prints your kids' open schoolwork every school day and shows it in a small app
on your own PC. Setup takes about 15 minutes. Nothing about your kids leaves your computer.

## What you need

- A Windows 10 or 11 PC that is on, and signed in, at the time you want the sheet to print.
- Your district's OneLogin **parent** username and password, the ones you use for Canvas and
  Home Access Center. If OneLogin texts you a code every time you sign in, the automatic
  refresh cannot work.
- A printer this PC can already print to.

The app comes set up for Lakota Local Schools. For another district, see
[Another school district](user-guide.md#24-another-school-district) in the user guide first.

## 1. Install

1. Open the [latest release](https://github.com/steiner385/fridgesheet/releases/latest) and,
   under **Assets**, download `FridgeSheet-Setup-<version>.exe`.
2. Run it. Windows says **"Windows protected your PC"** because the installer is not
   code-signed: click **More info**, then **Run anyway**.
3. Click through the installer. If you can, do this while signed in to a Windows account that
   is an administrator, so Fridge Sheet starts by itself every time you sign in.
4. When it finishes, the app opens in your web browser. Later, the **Fridge Sheet** shortcut
   on your desktop opens it.

## 2. Set it up

1. When the app asks **Who's looking?**, click **A grown-up**.
2. Click **Settings** in the list on the left. Under **School login**, type your OneLogin
   username and password, then click **Save** at the bottom.
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
7. On **Settings**, under **Updates**, set a **New update PIN** and click **Save**. When a
   new version comes out, an **Update** button then appears there.

That's it. The sheet prints on its own at the time you chose, and the app shows the same
list any time you open it.

## If something goes wrong

- **Diagnostics** (in the list on the left) checks everything and says what failed.
- **Runs** shows every sheet the app built or printed, with a **Reprint** button.
- **Help** (also in the list on the left) opens the full [user guide](user-guide.md);
  [Fridge Sheet for Windows](windows.md) covers Windows in detail, including uninstalling.
