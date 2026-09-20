"""One masked local dialog; transmit the token only over authenticated SSH stdin."""
import base64
import subprocess
import threading
import tkinter as tk
from tkinter import messagebox

REMOTE = r'''
import json, os, pathlib, sys, tempfile, urllib.request
root = pathlib.Path('/home/raspberry/CodexPi')
target = root / '.env'
old = target.read_text() if target.exists() else ''
if any(line.startswith('DISCORD_BOT_TOKEN=') and line.split('=',1)[1].strip() for line in old.splitlines()):
    print('already-configured')
    sys.exit(0)
token = sys.stdin.read().strip()
if not token or any(c.isspace() for c in token):
    sys.exit(2)
try:
    req = urllib.request.Request('https://discord.com/api/v10/users/@me',
          headers={'Authorization': 'Bot ' + token, 'User-Agent': 'CodexPi-Setup/1.0'})
    with urllib.request.urlopen(req, timeout=20) as response:
        user = json.load(response)
    if not user.get('bot'):
        sys.exit(2)
except Exception:
    sys.exit(3)
lines = [line for line in old.splitlines() if not line.startswith('DISCORD_BOT_TOKEN=')]
lines.append('DISCORD_BOT_TOKEN=' + token)
fd, temp = tempfile.mkstemp(prefix='.env-', dir=root)
try:
    with os.fdopen(fd, 'w') as handle:
        os.fchmod(handle.fileno(), 0o600)
        handle.write('\n'.join(lines) + '\n')
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, target)
    directory = os.open(root, os.O_DIRECTORY)
    os.fsync(directory)
    os.close(directory)
finally:
    if os.path.exists(temp): os.unlink(temp)
print('configured')
'''


def main():
    root = tk.Tk()
    root.title('CodexPi - Discord Bot-Token')
    root.geometry('540x190')
    root.resizable(False, False)
    tk.Label(root, text='Bestehenden Discord-Bot-Token einmalig eingeben.',
             font=('Segoe UI', 11)).pack(pady=(16, 6))
    tk.Label(root, text='Verdeckte Eingabe; Speicherung nur auf dem Raspberry Pi.').pack()
    value = tk.StringVar()
    entry = tk.Entry(root, textvariable=value, show='*', width=65)
    entry.pack(padx=20, pady=12)
    status = tk.StringVar(value='Token wird weder angezeigt noch protokolliert.')
    tk.Label(root, textvariable=status).pack()

    def save():
        token = value.get().strip()
        if not token:
            return
        value.set('')
        entry.configure(state='disabled')
        button.configure(state='disabled')
        status.set('Token wird geprueft und auf dem Pi gespeichert ...')

        def work():
            encoded = base64.b64encode(REMOTE.encode()).decode()
            command = 'python3 -c "import base64;exec(base64.b64decode(\'' + encoded + '\'))"'
            try:
                completed = subprocess.run(
                    ['ssh', '-o', 'BatchMode=yes', 'raspberry@192.168.2.105', command],
                    input=token.encode(), capture_output=True, timeout=45,
                    creationflags=subprocess.CREATE_NO_WINDOW)
                ok = completed.returncode == 0
            except Exception:
                ok = False

            def finish():
                if ok:
                    messagebox.showinfo('CodexPi', 'Bot-Token geprueft und sicher auf dem Pi gespeichert.')
                else:
                    messagebox.showerror('CodexPi', 'Pruefung oder Verbindung fehlgeschlagen. Kein Token wurde ausgegeben.')
                root.destroy()
            root.after(0, finish)
        threading.Thread(target=work, daemon=True).start()

    button = tk.Button(root, text='Pruefen und speichern', command=save)
    button.pack(pady=5)
    entry.focus_set()
    root.mainloop()


if __name__ == '__main__':
    main()
