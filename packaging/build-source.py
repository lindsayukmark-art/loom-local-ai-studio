"""Build the public source ZIP without personal data, weights, or binaries."""
from pathlib import Path
import hashlib
import sys

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
from studio.downloads import SOURCE_NAME, build_source_archive

destination = Path(sys.argv[1]) if len(sys.argv) > 1 else root / 'studio' / 'static' / 'releases' / SOURCE_NAME
destination.parent.mkdir(parents=True, exist_ok=True)
data = build_source_archive(root)
destination.write_bytes(data)
destination.with_suffix('.zip.sha256').write_text(f'{hashlib.sha256(data).hexdigest()}  {destination.name}\n', encoding='utf-8')
print(f'Created {destination} ({len(data):,} bytes)')
