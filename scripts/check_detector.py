"""Record the real first signal on frozen development fixtures; no accuracy claim."""
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import config
import detector

fixture_path = ROOT / 'examples/calibration.json'
samples = json.loads(fixture_path.read_text())['samples']
results = []
for sample in samples:
    started = time.monotonic()
    score = detector.model_signal(sample['text'])
    result = {'id': sample['id'], 'model_score': score, 'elapsed_seconds': round(time.monotonic()-started, 3)}
    results.append(result)
    print(json.dumps(result), flush=True)
out = ROOT / 'evidence/02-model-signal.json'
with out.open('x') as f:
    json.dump({'stage':'real unchanged detector before endpoint integration',
        'model':config.DETECTOR_MODEL,'fixtures_sha256':hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
        'results':results}, f, indent=2)
    f.write('\n')
