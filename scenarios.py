"""Frozen Unit 7 criteria translated into Unit 8 measurement scenarios.

The corpus is sourced human writing and disclosed AI examples, not the user's
own prose. Targets come from criteria.md without loosening them after results.
"""
import hashlib
import json
from pathlib import Path

import stylometry

ROOT = Path(__file__).resolve().parent
CORPUS = ROOT / 'examples/unit8_corpus.json'
CALIBRATION = ROOT / 'examples/calibration.json'
SCENARIOS = [
    {'criterion': 1, 'name': 'Human false positives', 'target': 'At most 1/20 human excerpts labelled ai'},
    {'criterion': 2, 'name': 'Mean score separation', 'target': 'Mean AI minus mean human score >= 0.20'},
    {'criterion': 3, 'name': 'Label coverage', 'target': '3/3 real labels; 1001/1001 grid points; invalid scores rejected'},
    {'criterion': 4, 'name': 'Persistent appeals', 'target': '10/10 exact appeals persist after restart; unknown 404; no rescoring'},
    {'criterion': 5, 'name': 'Bad-input safety', 'target': '13 field/media assertions + four byte-limit assertions; no inference or successful event'},
]


def load_corpus():
    return json.loads(CORPUS.read_text())


def calibration():
    return json.loads(CALIBRATION.read_text())['samples']


def validate():
    if not CORPUS.exists():
        return ['Missing frozen examples/unit8_corpus.json. Do not run before it is committed.']
    corpus = load_corpus()
    errors = []
    ids = []
    for group in ('human', 'ai'):
        rows = corpus.get(group, [])
        if len(rows) != 20:
            errors.append(f'{group}: need exactly 20 specimens')
        for row in rows:
            ids.append(row.get('id'))
            count = len(stylometry.words(row.get('text', '')))
            if not 80 <= count <= 220:
                errors.append(f"{row.get('id')}: {count} words outside 80–220")
            if not row.get('provenance') or not row.get('topic'):
                errors.append(f"{row.get('id')}: missing provenance/topic")
    if len(ids) != len(set(ids)):
        errors.append('Specimen IDs must be unique')
    human = corpus.get('human', [])
    if sum(r.get('genre') in ('plain', 'conventional', 'plain/conventional') for r in human) < 10:
        errors.append('Need at least ten plain/conventional human excerpts')
    if sum(r.get('genre') == 'formal' for r in human) < 5:
        errors.append('Need at least five formal human excerpts')
    return errors


def bad_input_cases(creator_prefix, content_id):
    """Thirteen exact criterion assertions, plus four byte-limit checks."""
    text = 'word ' * 25
    good = {'text': text, 'creator_id': creator_prefix}
    cases = [
        {'name': 'non_json', 'raw': b'hello', 'media': 'text/plain', 'expected': 415},
        {'name': 'malformed_json', 'raw': b'{"text":', 'expected': 400},
        {'name': 'array', 'json': [], 'expected': 400},
        {'name': 'missing_text', 'json': {'creator_id': creator_prefix + '-missing'}, 'expected': 400},
        {'name': 'numeric_text', 'json': {**good, 'text': 12}, 'expected': 400},
        {'name': 'blank_text', 'json': {**good, 'text': ' \n\t '}, 'expected': 400},
        {'name': 'nineteen_words', 'json': {**good, 'text': ' '.join(['word'] * 19)}, 'expected': 400},
        {'name': '10001_characters', 'json': {**good, 'text': ('word ' * 2001)[:10001]}, 'expected': 413},
        {'name': 'missing_creator', 'json': {'text': text}, 'expected': 400},
        {'name': 'numeric_creator', 'json': {**good, 'creator_id': 3}, 'expected': 400},
        {'name': 'blank_creator', 'json': {**good, 'creator_id': ' \t '}, 'expected': 400},
        {'name': 'long_creator', 'json': {**good, 'creator_id': 'x' * 101}, 'expected': 400},
        {'name': 'blank_appeal_reason', 'route': '/appeal', 'json': {'content_id': content_id, 'reasoning': ' \n '}, 'expected': 400},
    ]
    for chunked in (False, True):
        for media in ('application/json', 'text/plain'):
            cases.append({'name': f'oversize_{media}_{"chunked" if chunked else "length"}',
                          'raw': b'{"padding":"' + b'x' * 70000 + b'"}',
                          'media': media, 'chunked': chunked, 'expected': 413})
    return cases
