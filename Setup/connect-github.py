"""Transfer the already-authorized gh credential over SSH without printing it."""
import subprocess


def main():
    credential = subprocess.run(['gh', 'auth', 'token', '--hostname', 'github.com'],
                                capture_output=True, check=True).stdout
    if not credential.strip():
        raise SystemExit('No authenticated GitHub credential available')
    remote = ('umask 077; /home/raspberry/.local/bin/gh auth login '
              '--hostname github.com --git-protocol https --with-token && '
              'chmod 700 /home/raspberry/.config/gh && '
              'chmod 600 /home/raspberry/.config/gh/hosts.yml && '
              '/home/raspberry/.local/bin/gh auth setup-git && '
              '/home/raspberry/.local/bin/gh api user --jq .login')
    result = subprocess.run(['ssh', '-o', 'BatchMode=yes', 'raspberry@192.168.2.105', remote],
                            input=credential, capture_output=True)
    credential = b''
    if result.returncode:
        raise SystemExit('GitHub credential setup failed; no secret output displayed')
    print('Pi GitHub authenticated as ' + result.stdout.decode().strip())


if __name__ == '__main__':
    main()
