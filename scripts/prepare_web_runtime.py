"""Prepare Linux runtime dependencies without building the application or running package hooks."""
import argparse
from hashlib import sha256
from pathlib import Path
import shutil
import subprocess
import tarfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--node', required=True, type=Path)
    parser.add_argument('--npm-cli', required=True, type=Path)
    parser.add_argument('--destination', required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    # npm ci may replace this disposable dependency tree, never the user's checkout.
    stage = root / 'tmp/security-web-runtime-stage'
    if stage.is_symlink() or not stage.resolve().is_relative_to((root / 'tmp').resolve()):
        raise ValueError('Unsafe staging directory')
    stage.mkdir(parents=True, exist_ok=True)
    if (stage / 'node_modules').is_symlink():
        raise ValueError('Staging dependency directory cannot be a symlink')
    destination = args.destination.resolve()
    if not destination.is_relative_to((root / 'offline').resolve()):
        raise ValueError('Runtime archives must stay inside this workspace offline directory')
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise ValueError('Archive already exists; preserve it and select a fresh destination')
    for name in ['package.json', 'package-lock.json']:
        shutil.copyfile(root / 'web' / name, stage / name)
    (stage / 'scripts').mkdir(exist_ok=True)
    for name in ['patch-vinext-static-paths.mjs', 'verify-runtime-dependencies.mjs']:
        shutil.copyfile(root / 'web/scripts' / name, stage / 'scripts' / name)
    subprocess.run([str(args.node.resolve()), str(args.npm_cli.resolve()), 'ci', '--omit=dev', '--os=linux', '--cpu=x64', '--libc=glibc', '--ignore-scripts', '--no-fund', '--audit=false'], cwd=stage, check=True)
    digest = sha256((stage / 'package-lock.json').read_bytes()).hexdigest()
    if digest != sha256((root / 'web/package-lock.json').read_bytes()).hexdigest():
        raise ValueError('Lockfile changed while preparing the runtime')
    (stage / 'node_modules/.stl-runtime-lock.sha256').write_text(digest + '\n', encoding='utf-8')
    for name, extra in [('patch-vinext-static-paths.mjs', []), ('verify-runtime-dependencies.mjs', ['--linux', '--archive'])]:
        subprocess.run([str(args.node.resolve()), str(stage / 'scripts' / name), *extra], check=True, cwd=stage)
    def permissions(info):
        info.uid = info.gid = 0
        info.uname = info.gname = ''
        info.mode = 0o755 if info.isdir() else 0o644
        if info.isfile():
            with (stage / info.name).open('rb') as stream:
                signature = stream.read(4)
            if '/.bin/' in info.name or signature.startswith((b'#!', b'\x7fELF')):
                info.mode = 0o755
        return info
    with tarfile.open(destination, 'w:gz') as bundle:
        bundle.add(stage / 'node_modules', arcname='node_modules', filter=permissions)
    with destination.open('rb') as stream:
        archive_hash = sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            archive_hash.update(chunk)
    destination.with_suffix(destination.suffix + '.sha256').write_text(f'{archive_hash.hexdigest()}  {destination.name}\n', encoding='utf-8')
    print(f'Prepared {destination}; lock sha256 {digest}; archive sha256 {archive_hash.hexdigest()}')


if __name__ == '__main__':
    main()
