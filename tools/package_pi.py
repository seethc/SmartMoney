"""Build a source-only Pi bundle. Deliberately exclude databases and credentials."""
import io
import hashlib
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parent.parent
ROOT_FILES = ['run.py', 'start.sh', 'requirements.txt', 'requirements-lock.txt',
              'pyproject.toml', 'README.md', '.gitattributes', '.gitignore']
GROUPS = {'smartmoney':{'.py'}, 'tests':{'.py'}, 'tools':{'.py'}, 'docs':{'.md'},
          'frontend':{'.html','.css','.js','.svg','.png','.webmanifest'},
          'deploy':{'.sh','.service','.example'}}


def build():
    files = [ROOT/name for name in ROOT_FILES] + [ROOT/'frontend'/'sample-transactions.csv']
    for folder, suffixes in GROUPS.items():
        files.extend(p for p in (ROOT/folder).rglob('*')
                     if p.is_file() and p.suffix in suffixes and '__pycache__' not in p.parts)
    output = ROOT/'dist'/'smartmoney-rpi.tar.gz'
    output.parent.mkdir(exist_ok=True)
    with tarfile.open(output,'w:gz') as archive:
        for path in sorted(files):
            if path.is_symlink():
                raise RuntimeError('Packaging refuses symbolic links.')
            relative=path.relative_to(ROOT)
            data=path.read_bytes()
            if path.suffix != '.png':
                data=data.replace(b'\r\n',b'\n')
            info=tarfile.TarInfo('smartmoney/'+relative.as_posix())
            info.size=len(data)
            info.mode=0o755 if path.suffix=='.sh' else 0o644
            archive.addfile(info,io.BytesIO(data))
    print(f'Built {output.name}: {len(files)} source/assets files; no runtime data or credentials.')
    checksum = hashlib.sha256(output.read_bytes()).hexdigest()
    (output.parent/'smartmoney-rpi.sha256').write_text(checksum+'  '+output.name+'\n',encoding='ascii')
    (output.parent/'paste-into-pi-connect.txt').write_text(
        '# Large clipboard transfer retired after causing a remote-terminal stall.\n'
        '# Use the small LAN download command in docs/raspberry-pi.md instead.\n',encoding='utf-8')
    return output


if __name__=='__main__':
    build()
