"""Source-assisted retrieval experiment; all inputs and outputs stay outside Git.

Requires fdisbull[source], torch, transformers and an already downloaded encoder.
The manifest lists pinned source roots/paths/native targets and frozen questions.
No target, build script, compiler, or emulator is executed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import time

from fdisbull.source_catalog import SourceCatalog


def digest(path):
    sha = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(block)
    return sha.hexdigest()


def write(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


class Encoder:
    def __init__(self, path, model_name, revision):
        import torch
        import transformers
        from transformers import AutoModel, AutoTokenizer
        torch.set_num_threads(4)
        self.torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True, trust_remote_code=False)
        self.model = AutoModel.from_pretrained(path, local_files_only=True,
                                               trust_remote_code=False, use_safetensors=True).eval().to('cpu')
        artifacts = {p.relative_to(path).as_posix(): digest(p) for p in sorted(Path(path).rglob('*')) if p.is_file()}
        self.profile = dict(name=model_name, revision=revision, dimensions=self.model.config.hidden_size,
                            preprocessing=json.dumps(dict(
                                profile='attention-mask-mean-l2-256-cpu-fp32-v1',
                                torch=torch.__version__, transformers=transformers.__version__,
                                machine=platform.machine(), artifacts=artifacts), sort_keys=True))

    def encode(self, texts):
        torch = self.torch
        with torch.inference_mode():
            tokens = self.tokenizer(texts, padding=True, truncation=True, max_length=256, return_tensors='pt')
            hidden = self.model(**tokens).last_hidden_state
            mask = tokens['attention_mask'].unsqueeze(-1).to(hidden.dtype)
            pooled = (hidden * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
            return torch.nn.functional.normalize(pooled, p=2, dim=1).tolist()


def run(manifest_path, output, encoder_path, model_name, model_revision):
    manifest = json.loads(Path(manifest_path).read_text())
    questions = manifest['questions']
    # Freeze the input and labels before constructing the index or observing rankings.
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    write(output / 'frozen-manifest.json', manifest)
    started = time.perf_counter()
    binary_before = {str(s['target_path']): digest(s['target_path']) for s in manifest['sources']}
    source_snapshots, intake = [], []
    with SourceCatalog.create(output / 'sources.sqlite') as catalog:
        for source in manifest['sources']:
            head = subprocess.check_output(['git', '-C', source['root'], 'rev-parse', 'HEAD'], text=True).strip()
            if head != source['revision']:
                raise ValueError('source checkout differs from the pinned revision')
            subprocess.run(['git', '-C', source['root'], 'diff', '--no-ext-diff', '--quiet',
                            'HEAD', '--', *source['paths']], check=True)
            result = catalog.import_tree(**source)
            # Verify the captured bytes, not just a checkout's HEAD/name.
            batch = subprocess.run(['git', '-C', source['root'], 'cat-file', '--batch'],
                                   input=''.join(source['revision'] + ':' + p + '\n' for p in source['paths']).encode(),
                                   stdout=subprocess.PIPE, check=True).stdout
            position = 0
            stored = {r['path']: r['sha'] for r in catalog.db.execute(
                'SELECT path,sha FROM files WHERE snapshot=?', (result['id'],))}
            for path in source['paths']:
                end = batch.index(b'\n', position)
                header = batch[position:end].split()
                if len(header) != 3 or header[1] != b'blob':
                    raise ValueError('pinned source Git object is missing')
                size = int(header[2])
                position = end + 1
                if hashlib.sha256(batch[position:position + size]).hexdigest() != stored[path]:
                    raise ValueError('captured source bytes differ from the pinned Git object')
                position += size + 1
            checksum_lines = subprocess.check_output(['git', '-C', source['root'], 'show',
                                                      source['revision'] + ':civ.sha256'], text=True).splitlines()
            declared = [parts[0] for line in checksum_lines if len(parts := line.split()) == 2
                        and parts[1].lstrip('*').upper() == 'CIV.EXE']
            if declared != [source['declared_output_sha256']]:
                raise ValueError('declared target hash differs from pinned upstream checksum file')
            source_snapshots.append((source['edition'], result['id']))
            intake.append({k: v for k, v in result.items() if k != 'document'})
        parse_states = [dict(r) for r in catalog.db.execute(
            'SELECT snapshot,status,count(*) AS files,sum(errors) AS errors FROM files GROUP BY snapshot,status')]
        intake_seconds = time.perf_counter() - started
        encoder = Encoder(Path(encoder_path), model_name, model_revision)
        model = catalog.register_model(**encoder.profile)['id']
        began = time.perf_counter()
        while True:
            cards = catalog.cards(model=model, limit=32)['items']
            if not cards:
                break
            vectors = encoder.encode([c['text'] for c in cards])
            catalog.embed_cards(model, [dict(card=c['sha'], vector=v) for c, v in zip(cards, vectors)])
        embedding_seconds = time.perf_counter() - began
        rows, negative, query_vectors, query_embedding_seconds = [], [], [], 0.0
        for case in questions:
            began = time.perf_counter()
            vector = encoder.encode([case['query']])[0]
            query_embedding_seconds += time.perf_counter() - began
            query_vectors.append(dict(id=case['id'], vector=vector))
            for edition, snapshot in source_snapshots:
                for mode in ('lexical', 'vector', 'hybrid'):
                    began = time.perf_counter()
                    result = catalog.search(case['query'], mode=mode, model=model, vector=vector,
                                            snapshots=[snapshot], kind=case.get('kind'), limit=10)
                    elapsed = time.perf_counter() - began
                    expected = case.get('expected', [])
                    rank = next((i + 1 for i, item in enumerate(result['items'])
                                 if any(all(item.get(k) == v for k, v in selector.items()) for selector in expected)), None)
                    row = dict(case=case['id'], edition=edition, mode=mode, rank=rank,
                               seconds=elapsed, result=result)
                    (rows if expected else negative).append(row)
        # Concept descriptions/answers are added only after retrieval has been measured.
        concept = catalog.register_concept('city.food.stock', 'Accumulated food stored by a city',
                                           unit='food units', author='source-pilot')
        before_links = catalog.info()['counts']['cards']
        for edition, snapshot in source_snapshots:
            matches = [r for r in catalog.entities(snapshot=snapshot, name='food_box', kind='field')['items']
                       if r['owner'] == 'city']
            if len(matches) != 1:
                raise ValueError('food stock field is missing or ambiguous')
            catalog.link_concept(concept['id'], matches[0]['id'], 'represents',
                                 'Manual source review: struct city declaration labels food_box as accumulated food. '
                                 'Upstream is reconstructed source; native layout and behavior remain unqualified.',
                                 assurance='source-supported', author='source-pilot')
        assert catalog.info()['counts']['cards'] == before_links
        bindings = catalog.concept_bindings(concept['id'])
        occurrences = catalog.occurrences('food_box', limit=1000)
        counts = catalog.info()['counts']
        embedding_profile = catalog._model(model)['document']
    with SourceCatalog(output / 'sources.sqlite') as reopened:
        assert reopened.info()['counts'] == counts
        assert reopened.concept_bindings(concept['id']) == bindings
        assert reopened.db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert not reopened.db.execute('PRAGMA foreign_key_check').fetchall()
    binary_after = {p: digest(p) for p in binary_before}
    assert binary_before == binary_after
    metrics = {}
    for mode in ('lexical', 'vector', 'hybrid'):
        selected = [r for r in rows if r['mode'] == mode]
        metrics[mode] = dict(queries=len(selected),
                             hit_at_1=sum(r['rank'] == 1 for r in selected),
                             hit_at_3=sum(r['rank'] is not None and r['rank'] <= 3 for r in selected),
                             hit_at_10=sum(r['rank'] is not None for r in selected),
                             mrr_at_10=sum(1 / r['rank'] for r in selected if r['rank']) / len(selected),
                             search_seconds=sum(r['seconds'] for r in selected))
    report = dict(schema='fdisbull-source-search-pilot-1', created=datetime.now(timezone.utc).isoformat(),
                  manifest_sha256=digest(output / 'frozen-manifest.json'), source_intake=intake,
                  counts=counts, parse_states=parse_states, model=model,
                  embedding_profile=json.loads(embedding_profile), metrics=metrics,
                  intake_seconds=intake_seconds, embedding_seconds=embedding_seconds,
                  query_embedding_seconds=query_embedding_seconds,
                  concept_bindings=bindings, exact_food_box_occurrences=occurrences,
                  native_hashes_before=binary_before, native_hashes_after=binary_after,
                  restart_verified=True, sqlite_integrity='ok', native_execution=False,
                  pinned_source_bytes_verified=True,
                  source_build_verified=False, source_to_machine_mapping=False,
                  scope='Source-assisted retrieval sanity experiment across three DOS source editions; '
                        'labels were investigator-selected, not a blind benchmark. '
                        'No native equivalence, automatic binding resolution or UDL admission.')
    write(output / 'report.json', report)
    write(output / 'rankings.json', dict(answerable=rows, negative_controls=negative))
    write(output / 'query-vectors.json', dict(model=model, items=query_vectors))
    print(json.dumps(dict(output=str(output), counts=counts, metrics=metrics,
                          intake_seconds=intake_seconds, embedding_seconds=embedding_seconds), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--encoder-dir', required=True)
    parser.add_argument('--model-name', required=True)
    parser.add_argument('--model-revision', required=True)
    args = parser.parse_args()
    run(args.manifest, args.output, args.encoder_dir, args.model_name, args.model_revision)
