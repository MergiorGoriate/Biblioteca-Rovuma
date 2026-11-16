"""Prepare Railway's mounted volume and launch the web command as the app user."""

import os
import pwd
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile


def main():
    private = Path(os.environ.get("PRIVATE_ROOT", "/app/var/private"))
    volume = Path("/data")
    folders = (private, *(private / name for name in ("covers", "incoming", "versions")))

    if os.geteuid() == 0:
        user = pwd.getpwnam("rovuma")
        if not all(folder.resolve() == folder and folder.is_relative_to(volume) for folder in folders):
            raise RuntimeError("Defina PRIVATE_ROOT num directório privado no volume /data.")
        for folder in folders:
            folder.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chown(folder, user.pw_uid, user.pw_gid)
            folder.chmod(0o700)
        os.setgroups([])
        os.setgid(user.pw_gid)
        os.setuid(user.pw_uid)
        os.environ.update(HOME=user.pw_dir, USER=user.pw_name, LOGNAME=user.pw_name)

    for folder in folders:
        try:
            folder.mkdir(parents=True, exist_ok=True, mode=0o700)
            with NamedTemporaryFile(dir=folder, prefix=".storage-check-"):
                pass
        except OSError as error:
            print(
                f"Armazenamento privado sem acesso de escrita em {folder}: UID {os.geteuid()}, errno {error.errno}.",
                flush=True,
            )
            break
    else:
        print(f"Armazenamento de capas e documentos verificado com UID {os.geteuid()}.", flush=True)

    os.execvp(sys.argv[1], sys.argv[1:])


if __name__ == "__main__":
    main()
