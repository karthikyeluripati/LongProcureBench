"""Validate the 20-package Initial State v0.1 candidate, provenance, and missingness."""
import json
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker
from rfc3986_validator import validate_rfc3986

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / 'schema/initial-state.schema.json').read_text(encoding='utf-8'))
Draft202012Validator.check_schema(SCHEMA)
FORMAT_CHECKER = FormatChecker()


@FORMAT_CHECKER.checks('uri')
def valid_uri(value):
    # Explicit dependency and registration prevent silently skipped URI checks.
    return not isinstance(value, str) or bool(validate_rfc3986(value, rule='URI'))


VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FORMAT_CHECKER)


def pointer(record, path):
    if not path.startswith('/'):
        raise ValueError(f'Invalid JSON Pointer: {path}')
    value = record
    for part in path[1:].split('/'):
        part = part.replace('~1', '/').replace('~0', '~')
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def leaves(value, path=''):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from leaves(child, path + '/' + key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from leaves(child, path + '/' + str(index))
    else:
        yield path, value


def validate_record(record):
    VALIDATOR.validate(record)
    docs = {doc['document_id'] for doc in record['supporting_documents']}
    if len(docs) != len(record['supporting_documents']):
        raise ValueError('Duplicate document IDs')
    items = [item['item_id'] for item in record['line_items']]
    if len(items) != len(set(items)):
        raise ValueError('Duplicate item IDs')
    evidence_paths = []
    for evidence in record['source_provenance']:
        if evidence['document_id'] not in docs:
            raise ValueError('Unresolved provenance document')
        for path in evidence['field_paths']:
            if isinstance(pointer(record, path), (dict, list)):
                raise ValueError(f'Evidence must identify a scalar field: {path}')
            evidence_paths.append(path)
    missing = {entry['field_path'] for entry in record['missing_information']}
    for entry in record['missing_information']:
        value = pointer(record, entry['field_path'])
        if entry['reason'] in ('not_stated', 'bidder_to_provide', 'source_snapshot_unavailable') and value is not None:
            raise ValueError(f"Absence reason requires null: {entry['field_path']}")
    sourced = ('/project/', '/package_subscope', '/line_items/',
               '/total_estimated_budget', '/schedule/',
               '/supplier_eligibility_constraints', '/certifications_compliance',
               '/initial_state/source_issue_date')
    for path, value in leaves(record):
        if value is None and not path.endswith('/verbatim_excerpt') and path not in missing:
            raise ValueError(f'Unexplained null: {path}')
        if value is not None and path.startswith(sourced):
            if path not in evidence_paths:
                raise ValueError(f'Unsupported field: {path}')
    for item in record['line_items']:
        unit, total = item['estimated_unit_cost'], item['estimated_total_cost']
        if unit and total:
            if unit['currency'] != total['currency']:
                raise ValueError('Currency mismatch')
            if item['quantity'] is not None:
                if abs(unit['amount'] * item['quantity'] - total['amount']) > 0.01:
                    raise ValueError('Line estimate arithmetic mismatch')


def main():
    files = sorted((ROOT / 'data/initial_states/electrical').glob('*.json'))
    if len(files) != 20:
        raise ValueError(f'Initial State v0.1 requires exactly 20 packages; found {len(files)}')
    ids = set()
    count = 0
    for file in files:
        record = json.loads(file.read_text(encoding='utf-8'))
        validate_record(record)
        if record['package_id'] in ids or file.stem != record['package_id']:
            raise ValueError('Duplicate package ID or filename mismatch')
        ids.add(record['package_id'])
        count += len(record['line_items'])
        print(f'PASS {file.name}')
    print(f'Validated {len(files)} packages and {count} line items.')


if __name__ == '__main__':
    main()
